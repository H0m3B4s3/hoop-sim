"""Standings screen: both conferences side by side."""
from __future__ import annotations

from rich.columns import Columns

from hoopr.config import CONFERENCES
from hoopr.models.world import World
from hoopr.ui.console import clear, console, pause
from hoopr.ui.widgets import header, standings_table


def show_standings(world: World) -> None:
    clear()
    header(world)
    tables = [standings_table(world, conf) for conf in CONFERENCES]
    console.print(Columns(tables, padding=(0, 4), equal=True))
    console.print("[dim]● top-6 seed   ○ play-in (7–10)[/dim]")
    pause()
