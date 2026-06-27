"""Tactics screen: cycle the team's tactical settings."""
from __future__ import annotations

from rich.table import Table

from hoopsim.models.tactics import SETTINGS
from hoopsim.models.world import World
from hoopsim.ui.console import ask_int, clear, console
from hoopsim.ui.widgets import header


def edit_tactics(world: World) -> None:
    team = world.user_team
    keys = list(SETTINGS.keys())
    while True:
        clear()
        header(world)
        table = Table(title=f"{team.full_name} — Tactics", title_style="title",
                      header_style="label")
        table.add_column("#", justify="right")
        table.add_column("Setting")
        table.add_column("Current", style="accent")
        table.add_column("Options", style="dim")
        for i, (key, label, value) in enumerate(team.tactics.items(), start=1):
            table.add_row(str(i), label, value, " · ".join(SETTINGS[key]))
        console.print(table)
        console.print("[dim]Enter a setting # to cycle its value, or 0 to go back.[/dim]")
        choice = ask_int("Setting", default=0)
        if choice == 0:
            return
        if 1 <= choice <= len(keys):
            team.tactics.cycle(keys[choice - 1])
