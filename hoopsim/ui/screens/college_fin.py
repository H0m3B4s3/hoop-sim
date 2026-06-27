"""College financial screens: scholarship allocation (scholarship mode) or NIL deals (NIL mode)."""
from __future__ import annotations

from rich.panel import Panel
from rich.table import Table

from hoopsim.config import SCHOLARSHIP_LIMIT
from hoopsim.models.team import roster_players
from hoopsim.models.world import World
from hoopsim.systems import collegefin
from hoopsim.ui.console import ask_int, clear, console, pause
from hoopsim.ui.theme import ovr_style
from hoopsim.ui.widgets import class_label, header, money


def college_finance_screen(world: World) -> None:
    if world.college_economy == "nil":
        _nil_screen(world)
    else:
        _scholarship_screen(world)


# ---------------------------------------------------------------------------
# Scholarship mode
# ---------------------------------------------------------------------------
def _scholarship_screen(world: World) -> None:
    team = world.user_team
    clear()
    header(world)
    used = collegefin.scholarships_used(team)
    grid = Table.grid(padding=(0, 3))
    grid.add_column(style="label")
    grid.add_column(justify="right")
    grid.add_row("Scholarship limit", str(SCHOLARSHIP_LIMIT))
    grid.add_row("Scholarships used", str(used))
    grid.add_row("Open scholarships", f"[good]{collegefin.scholarships_open(team)}[/good]")
    console.print(Panel(grid, title=f"[title]{team.full_name} — Scholarships[/title]",
                        border_style=team.color))

    table = Table(title="Roster by Class", title_style="title", header_style="label")
    for col in ("Class", "Player", "Pos", "OVR", "POT"):
        table.add_column(col, justify="right" if col in ("OVR", "POT") else "left")
    players = sorted(roster_players(team, world.players),
                     key=lambda p: (-p.class_year, -p.overall))
    for p in players:
        table.add_row(class_label(p.class_year), p.name, p.position,
                      f"[{ovr_style(p.overall)}]{p.overall}[/]", str(p.scouted_potential()))
    console.print(table)
    console.print("[dim]Seniors graduate after this season; open scholarships are filled in "
                  "recruiting.[/dim]")
    pause()


# ---------------------------------------------------------------------------
# NIL mode
# ---------------------------------------------------------------------------
def _nil_screen(world: World) -> None:
    team = world.user_team
    while True:
        clear()
        header(world)
        grid = Table.grid(padding=(0, 3))
        grid.add_column(style="label")
        grid.add_column(justify="right")
        grid.add_row("NIL collective budget", money(team.nil_budget))
        grid.add_row("Committed to deals", money(collegefin.nil_spent(world, team)))
        grid.add_row("Available", f"[good]{money(collegefin.nil_available(world, team))}[/good]")
        console.print(Panel(grid, title=f"[title]{team.full_name} — NIL Collective[/title]",
                            border_style=team.color))

        table = Table(title="Player NIL Deals & Brand Value", title_style="title",
                      header_style="label")
        table.add_column("#", justify="right")
        for col in ("Player", "Yr", "Pos", "OVR", "Mkt"):
            table.add_column(col, justify="right" if col in ("OVR", "Mkt") else "left")
        table.add_column("NIL deal", justify="right")
        table.add_column("Brand value", justify="right")
        players = sorted(roster_players(team, world.players), key=lambda p: p.overall, reverse=True)
        for i, p in enumerate(players, start=1):
            deal = p.contract.current_salary
            table.add_row(str(i), p.name, class_label(p.class_year), p.position,
                          f"[{ovr_style(p.overall)}]{p.overall}[/]", str(p.ratings["marketability"]),
                          money(deal) if deal else "[dim]—[/dim]", money(p.brand_value))
        console.print(table)
        console.print("[dim]Enter a player # to offer/adjust an NIL deal, or 0 to go back.[/dim]")
        choice = ask_int("Player #", default=0)
        if choice == 0:
            return
        if 1 <= choice <= len(players):
            _offer_deal(world, team, players[choice - 1])


def _offer_deal(world: World, team, player) -> None:
    avail = collegefin.nil_available(world, team) + player.contract.current_salary
    console.print(f"[dim]{player.name} — available to allocate: {money(avail)}[/dim]")
    amount = ask_int("NIL deal amount ($, 0 to remove)", default=player.contract.current_salary or 100_000)
    ok, reason = collegefin.offer_nil_deal(world, team, player.pid, max(0, int(amount)))
    console.print(f"[good]{reason}[/good]" if ok else f"[bad]{reason}[/bad]")
    pause()
