"""Market-week chatbot: pull 6 days of prices with yfinance, compute returns, and have
Claude Sonnet 5 analyze the data."""

import os
import time
from pathlib import Path
from typing import Literal

import anthropic
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

MODEL = "claude-sonnet-5"
TICKERS = {
    "SPY": "US large-cap stocks (S&P 500)",
    "IEF": "7-10 year US Treasuries",
    "UUP": "US dollar index",
    "GLD": "Gold",
    "USO": "Crude oil",
}
DAYS = 6          # 6 closing prices -> 5 daily returns + the week's return
CACHE_SECONDS = 900

SYSTEM_PROMPT = """You are a markets analyst. You'll be given the past 6 trading days' \
closing prices and returns for SPY, IEF, UUP, GLD and USO. Analyze the data itself; don't \
describe or guess at news events.

What a good analysis covers:
- Which assets led and lagged, over the period and day by day, and how big the moves were.
- The cross-asset picture: stocks vs bonds (IEF rises when yields fall), the dollar, gold and \
oil, which moved together or against each other, and what that pattern suggests about the \
risk appetite, rate and inflation signals the data implies.
- Volatility: which assets were choppy vs steady, and any reversals.
- Lead with a 2-3 sentence summary, then the detail. Keep it tight; answer follow-ups conversationally.
- This is educational analysis, not personalized investment advice."""

ANALYSIS_REQUEST = "Here is this week's data. Please analyze it.\n\n{data}"


def _load_key() -> None:
    """Load the key from market-week/.env when it isn't already in the environment."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    env_file = Path(__file__).resolve().parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip().strip("\"'")


_load_key()
client = anthropic.Anthropic()

app = FastAPI(title="Market Week Chatbot")

PAGE = (Path(__file__).parent / "index.html").read_text()

_cache: dict = {"at": 0.0, "data": None}


def fetch_market_data() -> dict:
    """Last DAYS closes for each ticker, plus daily and full-period % returns."""
    if _cache["data"] and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["data"]

    # Pull a couple of weeks so holidays still leave us 6 trading days.
    df = yf.download(list(TICKERS), period="1mo", interval="1d",
                     auto_adjust=True, progress=False, threads=False)
    if df is None or df.empty:
        raise RuntimeError("yfinance returned no data.")
    closes = df["Close"][list(TICKERS)].dropna().tail(DAYS)
    if len(closes) < DAYS:
        raise RuntimeError(f"Only got {len(closes)} days of prices.")

    daily = closes.pct_change() * 100
    dates = [d.strftime("%a %b %d") for d in closes.index]
    assets = []
    for t in TICKERS:
        prices = closes[t].tolist()
        assets.append({
            "ticker": t,
            "name": TICKERS[t],
            "prices": [round(p, 2) for p in prices],
            "daily": [None] + [round(r, 2) for r in daily[t].iloc[1:]],
            "period": round((prices[-1] / prices[0] - 1) * 100, 2),
        })

    data = {"dates": dates, "start": closes.index[0].strftime("%Y-%m-%d"),
            "end": closes.index[-1].strftime("%Y-%m-%d"), "assets": assets}
    _cache.update(at=time.time(), data=data)
    return data


def format_for_prompt(data: dict) -> str:
    """Plain-text tables of prices and returns for the system prompt."""
    head = "Ticker".ljust(8) + "".join(d.rjust(12) for d in data["dates"])
    lines = [f"Closing prices, {data['start']} to {data['end']}:", head]
    for a in data["assets"]:
        lines.append(a["ticker"].ljust(8) + "".join(f"{p:12.2f}" for p in a["prices"]))
    lines += ["", "Daily returns (%):", head]
    for a in data["assets"]:
        cells = ["—".rjust(12)] + [f"{r:+12.2f}" for r in a["daily"][1:]]
        lines.append(a["ticker"].ljust(8) + "".join(cells))
    lines += ["", "Period return, first close to last close (%):"]
    for a in data["assets"]:
        lines.append(f"{a['ticker']:<6}{a['period']:+7.2f}   {a['name']}")
    return "\n".join(lines)


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=100)


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


@app.get("/api/market")
async def market():
    try:
        return await run_in_threadpool(fetch_market_data)
    except Exception as e:
        raise HTTPException(502, f"Couldn't load prices from yfinance: {e}")


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if req.messages[-1].role != "user":
        raise HTTPException(400, "The last message must come from the user.")
    try:
        data = await run_in_threadpool(fetch_market_data)
    except Exception as e:
        raise HTTPException(502, f"Couldn't load prices from yfinance: {e}")

    # The data rides in the first user turn, so every call sends it along with the ask.
    messages = [m.model_dump() for m in req.messages]
    messages[0]["content"] = (ANALYSIS_REQUEST.format(data=format_for_prompt(data))
                              + "\n\n" + messages[0]["content"])
    try:
        response = await run_in_threadpool(
            client.messages.create,
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            output_config={"effort": "medium"},
            messages=messages,
        )
    except anthropic.AuthenticationError:
        raise HTTPException(500, "The API key was rejected. Check market-week/.env.")
    except anthropic.RateLimitError:
        raise HTTPException(429, "Too many requests. Wait a moment and try again.")
    except anthropic.APIStatusError as e:
        raise HTTPException(502, f"Claude returned an error: {e.message}")
    except anthropic.APIConnectionError:
        raise HTTPException(502, "Couldn't reach the Anthropic API. Check your connection.")

    if response.stop_reason == "refusal":
        return {"reply": "I can't help with that one."}
    reply = "".join(b.text for b in response.content if b.type == "text").strip()
    return {"reply": reply or "I couldn't put together an answer. Try asking again."}
