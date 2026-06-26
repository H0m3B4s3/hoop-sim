"""Finances screen: payroll, cap position, luxury tax, and the contract ledger."""
from __future__ import annotations

from rich.panel import Panel
from rich.table import Table

from hoopr.models.team import roster_players
from hoopr.models.world import World
from hoopr.systems import cap
from hoopr.ui.console import clear, console, pause
from hoopr.ui.widgets import header, money


def show_finances(world: World) -> None:
    team = world.user_team
    clear()
    header(world)
    payroll = cap.payroll(world, team)
    space = cap.cap_space(world, team)
    tax = cap.luxury_tax(world, team)

    summary = Table.grid(padding=(0, 3))
    summary.add_column(style="label")
    summary.add_column(justify="right")
    summary.add_row("Payroll", money(payroll))
    summary.add_row("Salary cap", money(world.salary_cap))
    summary.add_row("Cap space", f"[good]{money(space)}[/good]" if space else "[dim]None[/dim]")
    summary.add_row("Luxury tax line", money(world.luxury_tax_line))
    summary.add_row("Luxury tax owed", f"[bad]{money(tax)}[/bad]" if tax else "[dim]None[/dim]")
    summary.add_row("Owner budget", money(team.owner_budget))
    console.print(Panel(summary, title=f"[title]{team.full_name} — Finances[/title]",
                        border_style=team.color))

    table = Table(title="Contracts", title_style="title", header_style="label")
    for col in ("Player", "Pos", "Age", "OVR", "Salary", "Yrs", "Market", "Surplus"):
        table.add_column(col, justify="right" if col not in ("Player", "Pos") else "left")
    players = sorted(roster_players(team, world.players),
                     key=lambda p: p.contract.current_salary, reverse=True)
    for p in players:
        market = cap.market_salary(p)
        surplus = market - p.contract.current_salary
        surplus_txt = (f"[good]+{money(surplus)}[/good]" if surplus >= 0
                       else f"[bad]-{money(-surplus)}[/bad]")
        table.add_row(p.name, p.position, str(p.age), str(p.overall),
                      money(p.contract.current_salary), str(p.contract.years_remaining),
                      money(market), surplus_txt)
    console.print(table)
    pause()
