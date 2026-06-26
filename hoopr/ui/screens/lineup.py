"""Lineup screen: set and lock the starting five, or revert to automatic selection."""
from __future__ import annotations



from rich.table import Table

from hoopr.models.attributes import POSITIONS
from hoopr.models.team import auto_set_lineup, position_distance
from hoopr.models.world import World
from hoopr.ui.console import choose, clear, console
from hoopr.ui.theme import ovr_style
from hoopr.ui.widgets import class_label, header


def lineup_screen(world: World) -> None:
    team = world.user_team
    while True:
        clear()
        header(world)
        _render(world, team)
        mode = "[good]manual[/good]" if not team.auto_lineup else "[dim]automatic[/dim]"
        console.print(f"  Lineup mode: {mode}\n")
        opts = [(f"slot:{i}", f"Change slot {i + 1} ({POSITIONS[i]})")
                for i in range(min(5, len(team.starters) or 5))]
        if not team.auto_lineup:
            opts.append(("auto", "↩  Revert to automatic lineup"))
        opts.append(("back", "← Back"))
        action = choose("", opts)
        if action == "back" or action is None:
            return
        if action == "auto":
            team.auto_lineup = True
            auto_set_lineup(team, world.players)
        elif action.startswith("slot:"):
            _change_slot(world, team, int(action.split(":")[1]))


def _render(world: World, team) -> None:
    table = Table(title=f"{team.full_name} — Starting Five", title_style="title",
                  header_style="label")
    for col in ("Slot", "Player", "Pos", "Fit", "OVR", "Min"):
        table.add_column(col, justify="right" if col in ("OVR", "Min") else "left")
    for i in range(5):
        slot = POSITIONS[i]
        if i < len(team.starters):
            p = world.players[team.starters[i]]
            fit = "natural" if position_distance(p, slot) == 0 else "[warn]off-pos[/warn]"
            yr = f" {class_label(p.class_year)}" if team.league == "college" else ""
            table.add_row(slot, f"{p.name}{yr}", p.position, fit,
                          f"[{ovr_style(p.overall)}]{p.overall}[/]",
                          str(team.minutes_target.get(p.pid, 0)))
        else:
            table.add_row(slot, "[dim]—[/dim]", "", "", "", "")
    console.print(table)
    bench = [world.players[pid] for pid in team.roster if pid not in team.starters]
    bench.sort(key=lambda p: p.overall, reverse=True)
    if bench:
        names = "  ".join(f"{p.short_name}([{ovr_style(p.overall)}]{p.overall}[/])" for p in bench)
        console.print(f"[dim]Bench:[/dim] {names}")


def _change_slot(world: World, team, slot_idx: int) -> None:
    pool = [world.players[pid] for pid in team.roster]
    pool.sort(key=lambda p: p.overall, reverse=True)
    current = team.starters[slot_idx] if slot_idx < len(team.starters) else None
    opts = []
    for p in pool:
        marker = " [star](starter)[/star]" if p.pid in team.starters else ""
        opts.append((str(p.pid), f"{p.name} [dim]{p.position} · OVR {p.overall}[/dim]{marker}"))
    pid = choose(f"Who starts at {POSITIONS[slot_idx]}?", opts, allow_back=True)
    if pid is None:
        return
    pid = int(pid)
    starters = list(team.starters)
    while len(starters) <= slot_idx:
        starters.append(None)
    if pid in starters:                 # already starting -> swap the two slots
        starters[starters.index(pid)] = current
    starters[slot_idx] = pid
    team.starters = [s for s in starters if s is not None]
    team.auto_lineup = False
    auto_set_lineup(team, world.players)
