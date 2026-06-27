"""Rich theme and shared style names used across screens."""
from __future__ import annotations

from rich.theme import Theme

HOOPSIM_THEME = Theme({
    "header": "bold white on grey23",
    "title": "bold cyan",
    "accent": "bold yellow",
    "good": "bold green",
    "bad": "bold red",
    "warn": "yellow",
    "dim": "grey58",
    "muted": "grey42",
    "label": "bold",
    "win": "green",
    "loss": "red",
    "money": "bold green",
    "injury": "red",
    "star": "bold yellow",
})


def ovr_style(ovr: int) -> str:
    """Colour an overall rating by tier."""
    if ovr >= 85:
        return "bold magenta"
    if ovr >= 78:
        return "bold cyan"
    if ovr >= 70:
        return "green"
    if ovr >= 62:
        return "white"
    return "grey58"
