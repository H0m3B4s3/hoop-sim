"""Reusable rich render helpers shared across screens (logic-free)."""
from __future__ import annotations

import time
from typing import List

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from hoopr.config import LUXURY_TAX_LINE, SALARY_CAP
from hoopr.models.league import Phase, conference_standings
from hoopr.models.player import Player
from hoopr.models.team import Team, roster_players, team_salary
from hoopr.models.world import World
from hoopr.sim.boxscore import GameResult
from hoopr.sim.season import game_date
from hoopr.ui.console import console
from hoopr.ui.theme import ovr_style


def money(value: int) -> str:
    return f"${value / 1_000_000:.1f}M"


def team_text(team: Team) -> Text:
    return Text(team.full_name, style=team.color)


# ---------------------------------------------------------------------------
# Status header
# ---------------------------------------------------------------------------
def header(world: World) -> None:
    team = world.user_team
    if team is None:
        return
    payroll = team_salary(team, world.players)
    cap_style = "money" if payroll <= SALARY_CAP else ("warn" if payroll <= LUXURY_TAX_LINE
                                                       else "bad")
    bits = [
        Text(team.full_name, style=f"bold {team.color}"),
        Text(f"  {game_date(world, world.day)}", style="dim"),
        Text(f"  {Phase.label(world.phase)}", style="accent"),
        Text(f"  {team.record_str}", style="label"),
        Text(f"  Payroll {money(payroll)}/{money(SALARY_CAP)}", style=cap_style),
    ]
    line = Text()
    for b in bits:
        line.append_text(b)
    console.print(Panel(line, style="header", padding=(0, 1)))


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------
def roster_table(world: World, team: Team, *, title: str = None) -> Table:
    table = Table(title=title or f"{team.full_name} — Roster", title_style="title",
                  header_style="label", expand=False)
    for col in ("#", "Name", "Pos", "Age", "OVR", "POT"):
        table.add_column(col, justify="right" if col in ("Age", "OVR", "POT") else "left")
    for col in ("PPG", "RPG", "APG", "Salary", "Yrs"):
        table.add_column(col, justify="right")
    table.add_column("Status", justify="left")

    players = sorted(roster_players(team, world.players), key=lambda p: p.overall, reverse=True)
    starters = set(team.starters)
    for p in players:
        s = p.season
        star = "[star]★[/star]" if p.pid in starters else " "
        status = "[injury]OUT %dg[/injury]" % p.injury.games_remaining if p.is_injured else ""
        name = f"{star} {p.name}"
        table.add_row(
            str(p.jersey), name, p.position, str(p.age),
            f"[{ovr_style(p.overall)}]{p.overall}[/]", str(p.scouted_potential()),
            f"{s.ppg:.1f}" if s.gp else "-", f"{s.rpg:.1f}" if s.gp else "-",
            f"{s.apg:.1f}" if s.gp else "-",
            money(p.contract.current_salary), str(p.contract.years_remaining), status,
        )
    return table


def player_card(world: World, p: Player) -> Panel:
    from hoopr.models.attributes import RATING_GROUPS
    grid = Table.grid(padding=(0, 2))
    grid.add_column(); grid.add_column(); grid.add_column(); grid.add_column()
    rows: List[List[str]] = []
    for group, keys in RATING_GROUPS.items():
        if group == "Marketability":
            continue
        for key in keys:
            val = p.ratings[key]
            rows.append([key.replace("_", " ").title(), f"[{ovr_style(val)}]{val}[/]"])
    # lay out in 2 columns of label/value pairs
    half = (len(rows) + 1) // 2
    for i in range(half):
        left = rows[i]
        right = rows[i + half] if i + half < len(rows) else ["", ""]
        grid.add_row(left[0], left[1], right[0], right[1])

    head = (f"[bold {ovr_style(p.overall)}]{p.name}[/]  {p.position} · {p.archetype}\n"
            f"[dim]{p.height_str} · {p.weight_lb} lb · Age {p.age} · "
            f"OVR {p.overall} · POT {p.scouted_potential()}[/]\n"
            f"Contract: {money(p.contract.current_salary)} × {p.contract.years_remaining}y")
    if p.is_injured:
        head += f"\n[injury]Injured: {p.injury.description} ({p.injury.games_remaining} games)[/]"
    border = world.teams[p.team_id].color if p.team_id in world.teams else "cyan"
    return Panel(grid, title=head, title_align="left", border_style=border)


# ---------------------------------------------------------------------------
# Standings
# ---------------------------------------------------------------------------
def standings_table(world: World, conference: str) -> Table:
    table = Table(title=f"{conference} Conference", title_style="title", header_style="label")
    table.add_column("#", justify="right")
    table.add_column("Team")
    table.add_column("W", justify="right")
    table.add_column("L", justify="right")
    table.add_column("Pct", justify="right")
    table.add_column("GB", justify="right")
    table.add_column("Strk", justify="right")
    teams = conference_standings(world.team_list(), conference)
    leader_wins = teams[0].wins if teams else 0
    leader_losses = teams[0].losses if teams else 0
    for i, t in enumerate(teams, start=1):
        gb = ((leader_wins - t.wins) + (t.losses - leader_losses)) / 2
        marker = "[good]●[/good]" if i <= 6 else ("[warn]○[/warn]" if i <= 10 else "  ")
        body = f"{t.abbrev}  {t.name}"
        if t.tid == world.user_team_id:
            body = f"[accent]{body}[/accent]"
        name = f"{marker} {body}"   # str cell -> Table parses the markup
        table.add_row(str(i), name, str(t.wins), str(t.losses), f"{t.win_pct:.3f}",
                      "-" if gb == 0 else f"{gb:.1f}", t.streak_str)
    return table


# ---------------------------------------------------------------------------
# Box score & play-by-play
# ---------------------------------------------------------------------------
def line_score_panel(world: World, result: GameResult) -> Panel:
    home, away = world.teams[result.home_tid], world.teams[result.away_tid]
    table = Table.grid(padding=(0, 1))
    periods = len(result.line_score)
    table.add_column("Team", justify="left")
    for i in range(periods):
        table.add_column(f"Q{i+1}" if i < 4 else f"OT{i-3}", justify="right")
    table.add_column("Final", justify="right")
    away_row = [away.abbrev] + [str(ls[1]) for ls in result.line_score] + [str(result.away_score)]
    home_row = [home.abbrev] + [str(ls[0]) for ls in result.line_score] + [str(result.home_score)]
    table.add_row(*away_row)
    table.add_row(*home_row)
    win = home if result.home_score > result.away_score else away
    return Panel(table, title=f"[accent]Final[/accent] — {win.full_name} win",
                 border_style=win.color)


def box_score_table(world: World, result: GameResult, tid: int) -> Table:
    team = world.teams[tid]
    table = Table(title=f"{team.abbrev} Box", title_style="title", header_style="label")
    for col in ("Player", "MIN", "PTS", "REB", "AST", "STL", "BLK", "TO", "FG", "3P", "FT", "+/-"):
        table.add_column(col, justify="right" if col != "Player" else "left")
    lines = [(pid, result.box[pid]) for pid in team.roster if pid in result.box]
    lines.sort(key=lambda kv: kv[1].secs, reverse=True)
    for pid, s in lines:
        if s.secs == 0:
            continue
        p = world.players[pid]
        pm = f"+{s.plus_minus}" if s.plus_minus > 0 else str(s.plus_minus)
        table.add_row(
            p.short_name, str(round(s.minutes)), f"[label]{s.pts}[/label]", str(s.reb),
            str(s.ast), str(s.stl), str(s.blk), str(s.tov),
            f"{s.fgm}/{s.fga}", f"{s.tpm}/{s.tpa}", f"{s.ftm}/{s.fta}", pm)
    return table


def bracket_panel(world: World) -> Panel:
    from hoopr.sim.playoffs import ROUND_LABELS
    b = world.bracket
    if not b:
        return Panel("No playoff bracket yet.", border_style="muted")
    seeds = b.get("seeds", {})
    table = Table.grid(padding=(0, 2))
    table.add_column()
    order = ["R1", "R2", "CF", "Finals"]
    by_round = {r: [] for r in order}
    for s in b.get("all_series", []):
        by_round.setdefault(s["round"], []).append(s)
    for rnd in order:
        series = by_round.get(rnd, [])
        if not series:
            continue
        table.add_row(Text(ROUND_LABELS.get(rnd, rnd), style="accent"))
        for s in series:
            hi, lo = world.teams[s["hi"]], world.teams[s["lo"]]
            hs, ls = seeds.get(str(s["hi"]), "?"), seeds.get(str(s["lo"]), "?")
            line = Text("  ")
            line.append(f"({hs}) {hi.abbrev} ", style=hi.color)
            line.append(f"{s['hi_w']}-{s['lo_w']} ", style="label")
            line.append(f"{lo.abbrev} ({ls})", style=lo.color)
            if s["winner"] is not None:
                w = world.teams[s["winner"]]
                line.append(f"  → {w.abbrev} advances", style="good")
            table.add_row(line)
    champ = b.get("champion")
    title = "Playoff Bracket"
    if champ is not None:
        title = f"[star]🏆 {world.teams[champ].full_name} — CHAMPIONS[/star]"
    return Panel(table, title=title, border_style="accent")


def play_by_play(world: World, result: GameResult, *, animate: bool = False,
                 delay: float = 0.0) -> None:
    home, away = world.teams[result.home_tid], world.teams[result.away_tid]
    last_q = 0
    for e in result.pbp:
        if e.quarter != last_q:
            last_q = e.quarter
            label = f"Quarter {e.quarter}" if e.quarter <= 4 else f"Overtime {e.quarter - 4}"
            console.rule(f"[accent]{label}[/accent]", style="muted")
        team = world.teams[e.tid] if e.tid is not None else None
        tag = f"[{team.color}]{team.abbrev}[/]" if team else "   "
        score = f"[dim]{away.abbrev} {e.away_score}-{e.home_score} {home.abbrev}[/dim]"
        console.print(f"  [dim]Q{e.quarter} {e.clock}[/dim]  {tag}  {e.text}   {score}")
        if animate and delay:
            time.sleep(delay)
