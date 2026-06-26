"""Free-agency screen: browse and sign available players within the cap."""
from __future__ import annotations

from rich.table import Table

from hoopr.models.world import World
from hoopr.systems import cap, freeagency
from hoopr.ui.console import ask_int, clear, confirm, console, pause
from hoopr.ui.theme import ovr_style
from hoopr.ui.widgets import header, money

_PAGE = 25


def free_agent_screen(world: World) -> None:
    team = world.user_team
    while True:
        clear()
        header(world)
        space = cap.cap_space(world, team)
        console.print(f"Cap space: [good]{money(space)}[/good]   "
                      f"Roster: {len(team.roster)}/15\n")
        fas = sorted(world.free_agent_players(), key=lambda p: p.overall, reverse=True)[:_PAGE]
        table = Table(title="Top Free Agents", title_style="title", header_style="label")
        table.add_column("#", justify="right")
        for col in ("Name", "Pos", "Age", "OVR", "POT"):
            table.add_column(col, justify="right" if col in ("Age", "OVR", "POT") else "left")
        table.add_column("Asking", justify="right")
        table.add_column("Sign?", justify="left")
        for i, p in enumerate(fas, start=1):
            salary = cap.market_salary(p)
            ok, _ = cap.can_sign(world, team, salary)
            table.add_row(str(i), p.name, p.position, str(p.age),
                          f"[{ovr_style(p.overall)}]{p.overall}[/]", str(p.scouted_potential()),
                          money(salary), "[good]✓[/good]" if ok else "[bad]✗[/bad]")
        console.print(table)
        console.print("[dim]Enter a player # to make an offer, or 0 to go back.[/dim]")
        choice = ask_int("Player #", default=0)
        if choice == 0:
            return
        if not (1 <= choice <= len(fas)):
            continue
        _attempt_sign(world, team, fas[choice - 1])


def _attempt_sign(world: World, team, player) -> None:
    salary, years = freeagency.offer_for(world, team, player)
    console.print(f"Offer to [accent]{player.name}[/accent]: "
                  f"[money]{money(salary)}[/money] × {years}y")
    if not confirm("Submit this offer?", default=True):
        return
    ok, reason = freeagency.sign_free_agent(world, team, player.pid, salary, years)
    if ok:
        console.print(f"[good]{player.name} signs with {team.abbrev}![/good] [dim]({reason})[/dim]")
    else:
        console.print(f"[bad]Cannot sign:[/bad] {reason}")
    pause()
