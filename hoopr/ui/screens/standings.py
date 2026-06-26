"""Standings screen: conferences side by side (works for NBA or college)."""
from __future__ import annotations

from rich.columns import Columns

from hoopr.config import CONFERENCES
from hoopr.models.world import World
from hoopr.ui.console import clear, console, pause
from hoopr.ui.widgets import header, standings_table


def world_conferences(world: World):
    if world.mode == "college":
        seen = []
        for t in world.team_list():
            if t.conference not in seen:
                seen.append(t.conference)
        return seen
    return list(CONFERENCES)


def show_standings(world: World) -> None:
    clear()
    header(world)
    confs = world_conferences(world)
    tables = [standings_table(world, conf) for conf in confs]
    console.print(Columns(tables, padding=(0, 3), equal=True))
    if world.mode == "college":
        console.print("[dim]● conference tournament seeds (top 8)[/dim]")
    else:
        console.print("[dim]● top-6 seed   ○ play-in (7–10)[/dim]")
    pause()
