"""Roster screen: view the roster table and drill into player cards."""
from __future__ import annotations

from typing import Optional

from hoopsim.models.team import Team
from hoopsim.models.world import World
from hoopsim.ui.console import ask_int, clear, console, pause
from hoopsim.ui.widgets import header, player_card, roster_table


def show_roster(world: World, team: Optional[Team] = None) -> None:
    team = team or world.user_team
    while True:
        clear()
        header(world)
        console.print(roster_table(world, team))
        console.print("[dim]Enter a jersey # to view a player, or 0 to go back.[/dim]")
        choice = ask_int("Player #", default=0)
        if choice == 0:
            return
        match = [p for p in (world.players[pid] for pid in team.roster) if p.jersey == choice]
        if not match:
            console.print("[bad]No player with that number.[/bad]")
            pause()
            continue
        clear()
        header(world)
        console.print(player_card(world, match[0]))
        pause()
