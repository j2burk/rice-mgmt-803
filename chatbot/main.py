"""A FastAPI chatbot: the browser POSTs the conversation, we ask Claude, and send back the reply."""

import os
from pathlib import Path
from typing import Literal

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

MODEL = "claude-sonnet-5"

PERSONA = """You are Chad, a stereotypical finance bro chatbot. You worked two years in \
investment banking, now "do PE", and bring it up constantly. Talk like it: "bro", "let's \
circle back", "move the needle", "synergies", "that's alpha", "risk-on", "EBITDA", "LFG". \
You love Patagonia vests, 5am workouts, cold plunges, and Excel shortcuts (never touch the mouse).

Stay in character, but stay genuinely helpful: under the bravado, give answers that are \
actually correct and useful. Keep replies short and punchy, a few sentences unless asked for more.
You are a parody, not a licensed advisor: never tell anyone to buy or sell a specific \
security or give personalized investment advice. If asked, joke about compliance killing \
the vibe and suggest they talk to an actual licensed advisor."""


def _load_key() -> None:
    """Load the key from chatbot/.env when it isn't already in the environment."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    env_file = Path(__file__).resolve().parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip().strip("\"'")


_load_key()
client = anthropic.Anthropic()

app = FastAPI(title="Finance Bro Chatbot")

PAGE = (Path(__file__).parent / "index.html").read_text()


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=10_000)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=100)


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if req.messages[-1].role != "user":
        raise HTTPException(400, "The last message must come from the user.")
    try:
        response = await run_in_threadpool(
            client.messages.create,
            model=MODEL,
            max_tokens=4096,
            system=PERSONA,
            output_config={"effort": "low"},
            messages=[m.model_dump() for m in req.messages],
        )
    except anthropic.AuthenticationError:
        raise HTTPException(500, "The API key was rejected. Check chatbot/.env.")
    except anthropic.RateLimitError:
        raise HTTPException(429, "Too many requests. Wait a moment and try again.")
    except anthropic.APIStatusError as e:
        raise HTTPException(502, f"Claude returned an error: {e.message}")
    except anthropic.APIConnectionError:
        raise HTTPException(502, "Couldn't reach the Anthropic API. Check your connection.")

    if response.stop_reason == "refusal":
        return {"reply": "Bro, compliance just walked by. I can't touch that one."}
    reply = "".join(block.text for block in response.content if block.type == "text")
    return {"reply": reply}
