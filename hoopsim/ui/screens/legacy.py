"""Legacy screen: Hall of Fame, all-time career leaders, and past champions/awards."""
from __future__ import annotations

from rich.table import Table

from hoopsim.models.world import World
from hoopsim.systems import legacy
from hoopsim.ui.console import choose, clear, console, pause
from hoopsim.ui.theme import ovr_style
from hoopsim.ui.widgets import header

_CATEGORIES = [("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"), ("gp", "Games")]


def legacy_screen(world: World) -> None:
    while True:
        clear()
        header(world)
        action = choose("Legacy & History", [
            ("hof", "🏅  Hall of Fame"),
            ("records", "📈  All-time leaders"),
            ("champions", "🏆  Past champions & awards"),
            ("back", "← Back"),
        ])
        if action == "hof":
            _hall_of_fame(world)
        elif action == "records":
            _records(world)
        elif action == "champions":
            _champions(world)
        else:
            return


def _accolade_str(accolades: dict) -> str:
    parts = [f"{v}× {legacy.ACCOLADE_LABELS.get(k, k)}"
             for k, v in sorted(accolades.items(), key=lambda kv: -legacy.ACCOLADE_WEIGHTS.get(kv[0], 0))
             if v]
    return " · ".join(parts)


def _hall_of_fame(world: World) -> None:
    clear()
    header(world)
    members = sorted(world.hall_of_fame, key=lambda s: s.get("hof_score", 0), reverse=True)
    if not members:
        console.print("[dim]No inductees yet — legends are enshrined when great careers end.[/dim]")
    else:
        table = Table(title="Hall of Fame", title_style="title", header_style="label")
        for col in ("Player", "Pos", "Peak", "Yrs", "PTS", "Accolades"):
            table.add_column(col, justify="right" if col in ("Peak", "Yrs", "PTS") else "left")
        for s in members:
            t = s.get("totals", {})
            table.add_row(
                s.get("name", "?"), s.get("position", ""),
                f"[{ovr_style(s.get('peak_ovr', 0))}]{s.get('peak_ovr', 0)}[/]",
                str(s.get("seasons", 0)), f"{t.get('pts', 0):,}",
                _accolade_str(s.get("accolades", {})) or "[dim]—[/dim]")
        console.print(table)
    pause()


def _records(world: World) -> None:
    for key, label in _CATEGORIES:
        rows = legacy.leaderboards(world, key, limit=10)
        if not rows:
            continue
        table = Table(title=f"All-Time {label}", title_style="title", header_style="label")
        table.add_column("#", justify="right")
        table.add_column("Player")
        table.add_column("Career")
        table.add_column(label, justify="right")
        for i, s in enumerate(rows, 1):
            tag = " 🏅" if s.get("hof") else (" [dim](active)[/dim]" if s.get("active") else "")
            span = f"{s.get('last_team', '')} · {s.get('first_year', '')}–{s.get('last_year', '')}"
            table.add_row(str(i), f"{s.get('name', '?')}{tag}", f"[dim]{span}[/dim]",
                          f"{s.get('totals', {}).get(key, 0):,}")
        console.print(table)
        console.print()
    if not world.retired and not any(p.career for p in world.players.values()):
        console.print("[dim]No completed seasons yet.[/dim]")
    pause()


def _champions(world: World) -> None:
    clear()
    header(world)
    if not world.history:
        console.print("[dim]No completed seasons yet — finish a season to crown a champion.[/dim]")
    else:
        table = Table(title="Champions & MVPs", title_style="title", header_style="label")
        for col in ("Year", "Champion", "MVP", "DPOY", "ROY"):
            table.add_column(col)
        for entry in reversed(world.history):
            awards = entry.get("awards") or {}

            def who(key: str) -> str:
                a = awards.get(key)
                return a.get("name", "—") if a else "[dim]—[/dim]"

            table.add_row(str(entry.get("year", "")), entry.get("champion_name", ""),
                          who("mvp"), who("dpoy"), who("roy"))
        console.print(table)
    pause()
