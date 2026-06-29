"""Reusable rich render helpers shared across screens (logic-free)."""
from __future__ import annotations

import time
from typing import List

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from hoopsim.config import SCHOLARSHIP_LIMIT
from hoopsim.models.league import Phase, conference_standings
from hoopsim.models.player import Player
from hoopsim.models.team import Team, roster_players, team_salary
from hoopsim.models.world import World
from hoopsim.sim.boxscore import GameResult
from hoopsim.sim.season import game_date
from hoopsim.ui.console import console
from hoopsim.ui.theme import ovr_style


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
    bits = [
        Text(team.full_name, style=f"bold {team.color}"),
        Text(f"  {game_date(world, world.day)}", style="dim"),
        Text(f"  {Phase.label(world.phase)}", style="accent"),
        Text(f"  {team.record_str}", style="label"),
    ]
    if world.mode == "college":
        from hoopsim.systems import collegefin
        if world.college_economy == "nil":
            spent = collegefin.nil_spent(world, team)
            bits.append(Text(f"  NIL {money(spent)}/{money(team.nil_budget)}", style="money"))
        else:
            bits.append(Text(f"  Schol {collegefin.scholarships_used(team)}/{SCHOLARSHIP_LIMIT}",
                             style="accent"))
        bits.append(Text(f"  Prestige {'★' * team.prestige}", style="star"))
    else:
        payroll = team_salary(team, world.players)
        cap_style = ("money" if payroll <= world.salary_cap
                     else "warn" if payroll <= world.luxury_tax_line else "bad")
        bits.append(Text(f"  Payroll {money(payroll)}/{money(world.salary_cap)}", style=cap_style))
        if world.phase == Phase.REGULAR_SEASON:
            from hoopsim.systems import trades
            if trades.trade_deadline_passed(world):
                bits.append(Text("  Deadline passed", style="bad"))
            else:
                left = trades.trade_deadline_day(world) - world.day
                style = "warn" if left <= 7 else "dim"
                bits.append(Text(f"  Trade deadline in {left}d", style=style))
    line = Text()
    for b in bits:
        line.append_text(b)
    console.print(Panel(line, style="header", padding=(0, 1)))


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------
def class_label(class_year: int) -> str:
    return {1: "Fr", 2: "So", 3: "Jr", 4: "Sr"}.get(class_year, "--")


def roster_table(world: World, team: Team, *, title: str = None) -> Table:
    college = team.league == "college"
    nil = college and world.college_economy == "nil"
    table = Table(title=title or f"{team.full_name} — Roster", title_style="title",
                  header_style="label", expand=False)
    for col in ("#", "Name", "Pos"):
        table.add_column(col, justify="left")
    table.add_column("Yr" if college else "Age", justify="right")
    for col in ("OVR", "POT", "PPG", "RPG", "APG"):
        table.add_column(col, justify="right")
    table.add_column("NIL" if nil else ("Schol" if college else "Salary"), justify="right")
    if not college:
        table.add_column("Yrs", justify="right")
    table.add_column("Status", justify="left")

    players = sorted(roster_players(team, world.players), key=lambda p: p.overall, reverse=True)
    starters = set(team.starters)
    for p in players:
        s = p.season
        star = "[star]★[/star]" if p.pid in starters else " "
        status = "[injury]OUT %dg[/injury]" % p.injury.games_remaining if p.is_injured else ""
        row = [str(p.jersey), f"{star} {p.name}", p.position,
               class_label(p.class_year) if college else str(p.age),
               f"[{ovr_style(p.overall)}]{p.overall}[/]", str(p.scouted_potential()),
               f"{s.ppg:.1f}" if s.gp else "-", f"{s.rpg:.1f}" if s.gp else "-",
               f"{s.apg:.1f}" if s.gp else "-"]
        if nil:
            row.append(money(p.contract.current_salary) if p.contract.current_salary else "-")
        elif college:
            row.append("[good]✓[/good]")
        else:
            row.append(money(p.contract.current_salary))
            row.append(str(p.contract.years_remaining))
        row.append(status)
        table.add_row(*row)
    return table


def player_card(world: World, p: Player) -> Panel:
    from hoopsim.models.attributes import RATING_GROUPS
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
    table.add_column("Net", justify="right")
    from hoopsim.sim import power
    pwr = power.power_map(world)
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
                      "-" if gb == 0 else f"{gb:.1f}", t.streak_str, _net_str(pwr.get(t.tid)))
    return table


def _net_str(pr) -> str:
    """Signed net rating with a color cue (green good / red bad), for the standings 'Net' column."""
    if pr is None:
        return "-"
    v = pr.power
    style = "good" if v > 0.5 else ("bad" if v < -0.5 else "muted")
    return f"[{style}]{v:+.1f}[/{style}]"


# ---------------------------------------------------------------------------
# Box score & play-by-play
# ---------------------------------------------------------------------------
def line_score_panel(world: World, result: GameResult) -> Panel:
    home = world.find_team(result.home_tid)
    away = world.find_team(result.away_tid)
    table = Table.grid(padding=(0, 1))
    periods = len(result.line_score)
    is_half = result.period_label == "half"
    reg, abbr = (2, "H") if is_half else (4, "Q")
    table.add_column("Team", justify="left")
    for i in range(periods):
        table.add_column(f"{abbr}{i+1}" if i < reg else f"OT{i-reg+1}", justify="right")
    table.add_column("Final", justify="right")
    away_row = [away.abbrev] + [str(ls[1]) for ls in result.line_score] + [str(result.away_score)]
    home_row = [home.abbrev] + [str(ls[0]) for ls in result.line_score] + [str(result.home_score)]
    table.add_row(*away_row)
    table.add_row(*home_row)
    win = home if result.home_score > result.away_score else away
    return Panel(table, title=f"[accent]Final[/accent] — {win.full_name} win",
                 border_style=win.color)


def box_score_table(world: World, result: GameResult, tid: int) -> Table:
    team = world.find_team(tid)
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
    from hoopsim.sim.playoffs import ROUND_LABELS
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


def _round_label(n_matchups: int) -> str:
    teams = n_matchups * 2
    return {2: "Final", 4: "Semifinals", 8: "Quarterfinals",
            16: "Round of 16", 32: "Round of 32"}.get(teams, f"Round of {teams}")


def _render_bracket_rounds(world: World, grid: Table, bracket: dict) -> None:
    for rnd in bracket["rounds"]:
        grid.add_row(Text("  " + _round_label(len(rnd)), style="dim"))
        for m in rnd:
            a, b = world.teams[m["a"]], world.teams[m["b"]]
            line = Text("    ")
            if m["winner"] is None:
                line.append(f"{a.abbrev}", style=a.color)
                line.append(" vs ", style="dim")
                line.append(f"{b.abbrev}", style=b.color)
            else:
                aw = m["winner"] == m["a"]
                line.append(f"{a.abbrev} {m['a_score']}", style="good" if aw else "dim")
                line.append("  ", style="dim")
                line.append(f"{b.abbrev} {m['b_score']}", style="good" if not aw else "dim")
            grid.add_row(line)


def college_bracket_panel(world: World) -> Panel:
    b = world.bracket
    if not b:
        return Panel("No tournament yet.", border_style="muted")
    grid = Table.grid(padding=(0, 2))
    grid.add_column()
    if b["stage"] == "conf":
        title = "Conference Tournaments"
        for conf, cb in b["conf"].items():
            grid.add_row(Text(conf, style="accent"))
            _render_bracket_rounds(world, grid, cb)
            if cb["champion"] is not None:
                grid.add_row(Text(f"  ✦ {world.teams[cb['champion']].abbrev} wins {conf}",
                                  style="good"))
    else:
        title = "National Tournament"
        if b.get("national"):
            _render_bracket_rounds(world, grid, b["national"])
    champ = b.get("champion")
    panel_title = title
    if champ is not None:
        panel_title = f"[star]🏆 {world.teams[champ].full_name} — NATIONAL CHAMPIONS[/star]"
    return Panel(grid, title=panel_title, border_style="accent")


def play_by_play(world: World, result: GameResult, *, animate: bool = False,
                 delay: float = 0.0) -> None:
    home, away = world.find_team(result.home_tid), world.find_team(result.away_tid)
    is_half = result.period_label == "half"
    reg, abbr = (2, "H") if is_half else (4, "Q")
    period_word = "Half" if is_half else "Quarter"
    last_q = 0
    for e in result.pbp:
        if e.quarter != last_q:
            last_q = e.quarter
            label = (f"{period_word} {e.quarter}" if e.quarter <= reg
                     else f"Overtime {e.quarter - reg}")
            console.rule(f"[accent]{label}[/accent]", style="muted")
        team = world.find_team(e.tid) if e.tid is not None else None
        tag = f"[{team.color}]{team.abbrev}[/]" if team else "   "
        score = f"[dim]{away.abbrev} {e.away_score}-{e.home_score} {home.abbrev}[/dim]"
        console.print(f"  [dim]{abbr}{e.quarter} {e.clock}[/dim]  {tag}  {e.text}   {score}")
        if animate and delay:
            time.sleep(delay)
