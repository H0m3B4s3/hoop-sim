"""Interactive draft screen: the user picks on the clock; the AI auto-picks otherwise."""
from __future__ import annotations

from typing import List, Tuple

from rich.panel import Panel
from rich.table import Table

from hoopr.models.world import World
from hoopr.systems import draft_system as D
from hoopr.ui.console import choose, clear, console, pause
from hoopr.ui.theme import ovr_style
from hoopr.ui.widgets import header

_BOARD = 14


def draft_screen(world: World) -> None:
    dc = world.draft_class
    if dc is None or dc.complete or dc.year != world.season_year:
        dc = D.setup_draft(world)

    recent: List[Tuple[int, int, int]] = []   # (pick_no, tid, pid) since user's last pick
    user_picks: List[Tuple[int, int]] = []     # (pick_no, pid)

    while not dc.complete:
        tid = dc.team_on_clock()
        if tid == world.user_team_id:
            _user_pick(world, dc, recent, user_picks)
            recent = []
        else:
            pick_no = dc.current_pick
            pid = D.ai_pick(world)
            recent.append((pick_no, tid, pid))

    D.undrafted_to_free_agents(world)
    _draft_recap(world, user_picks)


def _board_table(world: World, dc) -> Table:
    table = Table(title="Big Board — Best Available", title_style="title", header_style="label")
    table.add_column("Sel", justify="right")
    for col in ("Prospect", "Pos", "Age", "OVR", "POT"):
        table.add_column(col, justify="right" if col in ("Age", "OVR", "POT") else "left")
    remaining = sorted(dc.remaining_prospects(),
                       key=lambda pid: D.prospect_rank(world.players[pid]), reverse=True)[:_BOARD]
    for i, pid in enumerate(remaining, start=1):
        p = world.players[pid]
        table.add_row(str(i), f"{p.name} [dim]{p.archetype}[/dim]", p.position, str(p.age),
                      f"[{ovr_style(p.overall)}]{p.overall}[/]", str(p.scouted_potential()))
    return table


def _user_pick(world: World, dc, recent, user_picks) -> None:
    clear()
    header(world)
    if recent:
        lines = []
        for pick_no, tid, pid in recent:
            t, p = world.teams[tid], world.players[pid]
            lines.append(f"  #{pick_no} [{t.color}]{t.abbrev}[/] select {p.name} "
                         f"[dim]{p.position} OVR {p.overall}[/dim]")
        console.print(Panel("\n".join(lines), title="[dim]Picks since your last selection[/dim]",
                            border_style="muted"))
    console.print(f"[accent]You are on the clock — pick #{dc.current_pick}[/accent]")
    console.print(_board_table(world, dc))

    remaining = sorted(dc.remaining_prospects(),
                       key=lambda pid: D.prospect_rank(world.players[pid]), reverse=True)[:_BOARD]
    options = [(str(pid),
                f"{world.players[pid].name} [dim]{world.players[pid].position} · "
                f"OVR {world.players[pid].overall} · POT {world.players[pid].scouted_potential()}"
                f"[/dim]") for pid in remaining]
    options.append(("auto", "[dim]Auto-pick best available[/dim]"))
    key = choose("Make your selection", options)
    pid = D.best_available(world) if key == "auto" else int(key)
    pick_no = dc.current_pick
    D.make_pick(world, pid)
    user_picks.append((pick_no, pid))
    p = world.players[pid]
    console.print(Panel(f"[good]With pick #{pick_no}, you select {p.name}[/good]\n"
                        f"[dim]{p.position} · {p.archetype} · OVR {p.overall} · "
                        f"POT {p.scouted_potential()}[/dim]", border_style="good"))
    pause()


def _draft_recap(world: World, user_picks) -> None:
    clear()
    header(world)
    if not user_picks:
        console.print("[dim]Your team had no draft picks.[/dim]")
        pause()
        return
    table = Table(title="Your Draft Class", title_style="title", header_style="label")
    table.add_column("Pick", justify="right")
    for col in ("Player", "Pos", "Age", "OVR", "POT"):
        table.add_column(col, justify="right" if col in ("Age", "OVR", "POT") else "left")
    for pick_no, pid in user_picks:
        p = world.players[pid]
        table.add_row(f"#{pick_no}", p.name, p.position, str(p.age),
                      f"[{ovr_style(p.overall)}]{p.overall}[/]", str(p.scouted_potential()))
    console.print(table)
    pause()
