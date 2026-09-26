from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse

from themes import theme_for

app = FastAPI(title="Countdown")

PAGE = (Path(__file__).parent / "index.html").read_text()


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


@app.get("/api/countdown")
async def countdown(
    target: datetime = Query(..., description="ISO 8601 timestamp"),
    occasion: str = Query("", max_length=200),
):
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    seconds = (target - datetime.now(timezone.utc)).total_seconds()
    if seconds < 0:
        raise HTTPException(400, "That date is in the past. Pick a future date.")
    theme, source = await run_in_threadpool(theme_for, occasion)
    return {"seconds": int(seconds), "theme": theme.model_dump(), "theme_source": source}
