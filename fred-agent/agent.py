"""FRED agent built on the Claude Agent SDK.

Tools: the FRED MCP server (its only data source) and a local run_python tool.
Usage: .venv/bin/python agent.py "your question"
"""

import asyncio
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool,
)

HERE = Path(__file__).parent
OUTPUT_DIR = HERE / "output"
load_dotenv(HERE / ".env")

SYSTEM_PROMPT = f"""You are an economic data analyst.

Your only source of data is the FRED MCP server (tools named mcp__fred__*). Do not use
figures from memory; every number you report or plot must come from a FRED tool call.

You also have run_python, which runs a Python script and returns its stdout and stderr.
pandas and matplotlib are installed. The script cannot reach the internet, so put the
data you got from FRED into the script. Save any charts as PNG files in the current
directory (it is {OUTPUT_DIR}) and print the file name. Each call starts fresh.

When you finish, say what you plotted, which FRED series you used, and the date range."""


@tool(
    "run_python",
    "Run a Python script in a fresh process and return its stdout and stderr. "
    "pandas and matplotlib are available. Save files to the current directory.",
    {"code": str},
)
async def run_python(args):
    OUTPUT_DIR.mkdir(exist_ok=True)
    try:
        proc = subprocess.run(
            [sys.executable, "-c", args["code"]],
            cwd=OUTPUT_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env={"MPLBACKEND": "Agg", "PATH": "/usr/bin:/bin"},
        )
    except subprocess.TimeoutExpired:
        return {"content": [{"type": "text", "text": "Timed out after 120 s."}], "is_error": True}
    out = f"exit code {proc.returncode}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    return {"content": [{"type": "text", "text": out[-20000:]}], "is_error": proc.returncode != 0}


OPTIONS = ClaudeAgentOptions(
    model="claude-opus-5",
    system_prompt=SYSTEM_PROMPT,
    tools=[],  # no built-in Claude Code tools (no Bash, Read, WebSearch, ...)
    mcp_servers={
        "fred": {"type": "http", "url": "https://fred.kerryback.com/mcp"},
        "python": create_sdk_mcp_server("python", tools=[run_python]),
    },
    allowed_tools=["mcp__fred", "mcp__python__run_python"],
    strict_mcp_config=True,  # ignore any other MCP servers configured on this machine
    setting_sources=[],  # ignore user/project Claude Code settings
    max_turns=30,
    cwd=str(HERE),
)


async def main(prompt: str):
    async for message in query(prompt=prompt, options=OPTIONS):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)
                elif isinstance(block, ToolUseBlock):
                    print(f"\n[tool] {block.name} {str(block.input)[:200]}\n")
        elif isinstance(message, ResultMessage):
            print(f"\n[done] turns={message.num_turns} cost=${message.total_cost_usd or 0:.4f}")


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or (
        "Plot the US unemployment rate and CPI inflation (year-over-year %) over the "
        "last ten years on one chart."
    )
    asyncio.run(main(prompt))
