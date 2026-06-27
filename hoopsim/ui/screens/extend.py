"""Re-sign / extend screen: lock up your own players with a contract extension (Bird rights)."""
from __future__ import annotations

from rich.table import Table

from hoopsim.models.team import roster_players
from hoopsim.models.world import World
from hoopsim.systems import cap
from hoopsim.ui.console import ask_int, clear, confirm, console, pause
from hoopsim.ui.widgets import header, money


def extend_screen(world: World) -> None:
    team = world.user_team
    while True:
        clear()
        header(world)
        console.print(f"[dim]Cap {money(world.salary_cap)} · Tax line "
                      f"{money(world.luxury_tax_line)} · own players can be extended over the cap "
                      f"(Bird rights).[/dim]\n")
        players = sorted(roster_players(team, world.players),
                         key=lambda p: p.contract.years_remaining)
        table = Table(title="Roster — Contracts", title_style="title", header_style="label")
        table.add_column("#", justify="right")
        for col in ("Player", "Pos", "Age", "OVR"):
            table.add_column(col, justify="right" if col in ("Age", "OVR") else "left")
        table.add_column("Salary", justify="right")
        table.add_column("Yrs", justify="right")
        table.add_column("Extend?", justify="left")
        for i, p in enumerate(players, start=1):
            ok, _ = cap.can_extend(world, team, p.pid)
            expiring = "[warn]expiring[/warn]" if p.contract.years_remaining <= 1 else ""
            table.add_row(str(i), p.name, p.position, str(p.age), str(p.overall),
                          money(p.contract.current_salary), str(p.contract.years_remaining),
                          ("[good]✓[/good] " + expiring) if ok else "[dim]max length[/dim]")
        console.print(table)
        console.print("[dim]Enter a player # to extend/re-sign, or 0 to go back.[/dim]")
        choice = ask_int("Player #", default=0)
        if choice == 0:
            return
        if 1 <= choice <= len(players):
            _extend(world, team, players[choice - 1])


def _extend(world: World, team, player) -> None:
    ok, reason = cap.can_extend(world, team, player.pid)
    if not ok:
        console.print(f"[bad]{reason}[/bad]")
        pause()
        return
    sal, years = cap.extension_offer(world, player)
    max_sal = cap.max_salary(player.experience, world.salary_cap)
    console.print(f"[dim]{player.name}: market ~{money(sal)}, max {money(max_sal)}.[/dim]")
    salary = ask_int("Annual salary ($)", default=sal)
    add_years = ask_int("Additional years", default=years)
    if not confirm(f"Extend {player.name} for {money(salary)} × {add_years}y?", default=True):
        return
    ok, msg = cap.extend_contract(world, team, player.pid, salary, add_years)
    console.print(f"[good]{msg}[/good]" if ok else f"[bad]{msg}[/bad]")
    pause()
