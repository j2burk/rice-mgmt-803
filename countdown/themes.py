"""Have Claude design a visual theme for any occasion, with a plain default if it can't."""

import os
import re
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, Field


class Theme(BaseModel):
    hero: str = Field(description="1-3 emoji that best picture the occasion, shown large")
    tagline: str = Field(description="Short, warm subtitle (under 60 chars). May use {year} for the target year.")
    bg_from: str = Field(description="Background gradient start, hex like #112233")
    bg_to: str = Field(description="Background gradient end, hex")
    text: str = Field(description="Main text color, hex; must be highly readable on the background")
    accent: str = Field(description="Accent color for numbers and highlights, hex")
    card: str = Field(description="Countdown box background, hex; subtle contrast against the background")
    font: Literal["serif", "sans", "script", "display", "mono"]
    effect: Literal["snow", "confetti", "floating", "sparkle", "none"] = Field(
        description="snow = gentle drifting fall, confetti = tumbling fall, floating = rising, sparkle = twinkling in place"
    )
    particles: list[str] = Field(description="1-4 emoji used for the particle effect")


DEFAULT = Theme(
    hero="⏳", tagline="Counting every second",
    bg_from="#0F172A", bg_to="#1E293B",
    text="#E2E8F0", accent="#38BDF8", card="#1E293B",
    font="sans", effect="sparkle", particles=["✨"],
)

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_cache: dict[str, Theme] = {}


def _load_key() -> None:
    """Load the key from countdown/.env when it isn't already in the environment."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    env_file = Path(__file__).resolve().parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip().strip("\"'")


_load_key()
_client = anthropic.Anthropic() if os.environ.get("ANTHROPIC_API_KEY") else None


def _clean(theme: Theme) -> Theme:
    for field in ("bg_from", "bg_to", "text", "accent", "card"):
        if not HEX.match(getattr(theme, field)):
            setattr(theme, field, getattr(DEFAULT, field))
    theme.particles = theme.particles[:4] or DEFAULT.particles
    return theme


def _ask_claude(occasion: str) -> Theme | None:
    if _client is None:
        return None
    try:
        response = _client.messages.parse(
            model="claude-opus-5",
            max_tokens=4000,
            output_config={"effort": "low"},
            system=(
                "You design the look of a countdown page for an occasion someone is looking forward to. "
                "Make it feel specific to the occasion: use the real colors of any named school, team, "
                "brand, holiday or culture, and choose emoji, font and effect that fit its mood. "
                "Keep text highly readable against the background, and make the accent readable on both the "
                "background and the card color."
            ),
            messages=[{"role": "user", "content": f"Occasion: {occasion}"}],
            output_format=Theme,
        )
    except anthropic.APIError:
        return None
    if response.stop_reason != "end_turn" or response.parsed_output is None:
        return None
    return _clean(response.parsed_output)


def theme_for(occasion: str) -> tuple[Theme, str]:
    """Return the theme and where it came from: claude or default."""
    occasion = occasion.strip()
    if not occasion:
        return DEFAULT, "default"
    key = occasion.lower()
    if key not in _cache:
        theme = _ask_claude(occasion)
        if theme is None:
            return DEFAULT, "default"
        _cache[key] = theme
    return _cache[key], "claude"
