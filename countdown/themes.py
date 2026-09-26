"""Have Claude design a visual theme for any occasion, with a plain default if it can't."""

import colorsys
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
    bg_from="#6D28D9", bg_to="#DB2777",
    text="#FFFFFF", accent="#FDE047", card="#4C1D95",
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


def _vivid(hex_color: str) -> str:
    """Lift a muted, grayish or near-black color to a saturated, mid-bright version of the same hue."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(h, min(max(l, 0.3), 0.62), max(s, 0.75))
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


def _luminance(hex_color: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(int(hex_color[i:i + 2], 16) / 255) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _clean(theme: Theme) -> Theme:
    for field in ("bg_from", "bg_to", "text", "accent", "card"):
        if not HEX.match(getattr(theme, field)):
            setattr(theme, field, getattr(DEFAULT, field))
    theme.bg_from, theme.bg_to = _vivid(theme.bg_from), _vivid(theme.bg_to)
    # Brightening the background can undo Claude's contrast; fall back to white or near-black text.
    if min(_contrast(theme.text, theme.bg_from), _contrast(theme.text, theme.bg_to)) < 4:
        dark = "#111827"
        worst = lambda c: min(_contrast(c, theme.bg_from), _contrast(c, theme.bg_to))
        theme.text = "#FFFFFF" if worst("#FFFFFF") >= worst(dark) else dark
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
                "The background must be vivid and saturated: bold, bright, energetic hues, with the two "
                "gradient colors clearly different from each other. Never use muted, dusty, pastel-gray, "
                "or near-black backgrounds; for a school or brand, use the brightest version of its colors. "
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
