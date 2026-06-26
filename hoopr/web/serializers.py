"""Turn World/Team/Player/GameResult into plain JSON-able dicts for the web API.

This is the web analogue of ``hoopr.ui.widgets``: where the terminal builds ``rich`` tables,
here we emit dicts of the *same computed numbers* and let the browser handle formatting and
sorting. We deliberately reuse the models' computed properties and the existing engine helpers
(``conference_standings``, ``cap`` math, ``team_salary``) rather than recomputing anything.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict, List, Optional

from rich.color import Color

from hoopr.config import CONFERENCES, ROSTER_MAX, SCHOLARSHIP_LIMIT
from hoopr.models.attributes import COMPOSITES, RATING_GROUPS, all_composites
from hoopr.models.league import Phase, conference_standings
from hoopr.models.player import Player
from hoopr.models.team import Team, roster_players, team_salary
from hoopr.models.world import World
from hoopr.sim.boxscore import GameResult
from hoopr.sim.season import game_date
from hoopr.systems import cap


# ---------------------------------------------------------------------------
# Colors — resolve rich named colors (e.g. "navy_blue") to CSS hex.
# ---------------------------------------------------------------------------
@lru_cache(maxsize=256)
def color_hex(name: str) -> str:
    try:
        r, g, b = Color.parse(name).get_truecolor()
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:  # noqa: BLE001 - unknown color name; fall back to a neutral
        return "#9aa0a6"


# ---------------------------------------------------------------------------
# Teams & world summary
# ---------------------------------------------------------------------------
def team_brief(team: Team) -> dict:
    """Minimal team identity used for dropdowns, opponent labels, and table cells."""
    return {
        "tid": team.tid,
        "abbrev": team.abbrev,
        "name": team.name,
        "city": team.city,
        "full_name": team.full_name,
        "conference": team.conference,
        "color": color_hex(team.color),
        "league": team.league,
        "prestige": team.prestige,
        "market_size": team.market_size,
    }


def world_conferences(world: World) -> List[str]:
    """Conference names in a stable order (mirrors ui.screens.standings.world_conferences)."""
    if world.mode == "college":
        seen: List[str] = []
        for t in world.team_list():
            if t.conference not in seen:
                seen.append(t.conference)
        return seen
    return list(CONFERENCES)


def world_summary(world: World) -> dict:
    """The status-bar payload (mirrors ui.widgets.header)."""
    team = world.user_team
    out = {
        "season_year": world.season_year,
        "phase": world.phase,
        "phase_label": Phase.label(world.phase),
        "day": world.day,
        "date": game_date(world, world.day),
        "mode": world.mode,
        "college_economy": world.college_economy,
        "user_team_id": world.user_team_id,
        "salary_cap": world.salary_cap,
        "luxury_tax_line": world.luxury_tax_line,
        "teams": [team_brief(t) for t in sorted(world.team_list(), key=lambda t: t.full_name)],
        "conferences": world_conferences(world),
    }
    if team is not None:
        out["user_team"] = team_brief(team)
        out["record"] = team.record_str
        if world.mode == "college":
            from hoopr.systems import collegefin
            if world.college_economy == "nil":
                out["nil_spent"] = collegefin.nil_spent(world, team)
                out["nil_budget"] = team.nil_budget
            else:
                out["scholarships_used"] = collegefin.scholarships_used(team)
                out["scholarship_limit"] = SCHOLARSHIP_LIMIT
        else:
            out["payroll"] = team_salary(team, world.players)
    return out


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------
def player_row(world: World, p: Player, *, is_starter: bool = False) -> dict:
    """A roster/list row (mirrors ui.widgets.roster_table). Raw numbers; UI formats them."""
    s = p.season
    team = world.find_team(p.team_id) if p.team_id is not None else None
    return {
        "pid": p.pid,
        "jersey": p.jersey,
        "name": p.name,
        "short_name": p.short_name,
        "position": p.position,
        "secondary_position": p.secondary_position,
        "archetype": p.archetype,
        "age": p.age,
        "class_year": p.class_year,
        "overall": p.overall,
        "potential": p.scouted_potential(),
        "ppg": round(s.ppg, 1),
        "rpg": round(s.rpg, 1),
        "apg": round(s.apg, 1),
        "gp": s.gp,
        "salary": p.contract.current_salary,
        "years_remaining": p.contract.years_remaining,
        "is_starter": is_starter,
        "is_injured": p.is_injured,
        "injury": (p.injury.description if p.is_injured else None),
        "injury_games": (p.injury.games_remaining if p.is_injured else 0),
        "team_id": p.team_id,
        "team_abbrev": (team.abbrev if team else "FA"),
        "team_color": (color_hex(team.color) if team else "#9aa0a6"),
    }


def roster_view(world: World, team: Team) -> dict:
    starters = set(team.starters)
    players = sorted(roster_players(team, world.players), key=lambda p: p.overall, reverse=True)
    rows = [player_row(world, p, is_starter=p.pid in starters) for p in players]
    return {
        "team": team_brief(team),
        "players": rows,
        "roster_max": ROSTER_MAX,
        "starters": list(team.starters),
        "auto_lineup": team.auto_lineup,
    }


def player_detail(world: World, p: Player) -> dict:
    """Full ratings card (mirrors ui.widgets.player_card) plus season/career stats."""
    groups = {
        group: [{"key": k, "label": k.replace("_", " ").title(), "value": p.ratings[k]}
                for k in keys]
        for group, keys in RATING_GROUPS.items()
        if group != "Marketability" or world.mode == "college"
    }
    composites = {name: round(v, 1) for name, v in all_composites(p.ratings).items()}
    s = p.season
    base = player_row(world, p)
    base.update({
        "height": p.height_str,
        "weight_lb": p.weight_lb,
        "experience": p.experience,
        "college": p.college,
        "morale": p.morale,
        "rating_groups": groups,
        "composites": composites,
        "composite_order": list(COMPOSITES),
        "season_stats": {
            "gp": s.gp, "gs": s.gs, "mpg": round(s.mpg, 1), "ppg": round(s.ppg, 1),
            "rpg": round(s.rpg, 1), "apg": round(s.apg, 1),
            "spg": round(s.per_game("stl"), 1), "bpg": round(s.per_game("blk"), 1),
            "topg": round(s.per_game("tov"), 1),
            "fg_pct": round(s.fg_pct, 3), "tp_pct": round(s.tp_pct, 3),
            "ft_pct": round(s.ft_pct, 3), "ts_pct": round(s.ts_pct, 3),
        },
        "career": list(p.career),
    })
    return base


# ---------------------------------------------------------------------------
# Standings & leaders
# ---------------------------------------------------------------------------
def standings_view(world: World) -> dict:
    """Conference standings with GB and seed markers (mirrors ui.widgets.standings_table)."""
    confs = []
    for conf in world_conferences(world):
        teams = conference_standings(world.team_list(), conf)
        leader_w = teams[0].wins if teams else 0
        leader_l = teams[0].losses if teams else 0
        rows = []
        for i, t in enumerate(teams, start=1):
            gb = ((leader_w - t.wins) + (t.losses - leader_l)) / 2
            rows.append({
                "rank": i,
                "tid": t.tid,
                "abbrev": t.abbrev,
                "name": t.name,
                "color": color_hex(t.color),
                "wins": t.wins,
                "losses": t.losses,
                "win_pct": round(t.win_pct, 3),
                "gb": round(gb, 1),
                "streak": t.streak_str,
                "point_diff": t.point_diff,
                "is_user": t.tid == world.user_team_id,
            })
        confs.append({"conference": conf, "teams": rows})
    return {"mode": world.mode, "conferences": confs}


_LEADER_STATS = [
    ("ppg", "PPG"), ("rpg", "RPG"), ("apg", "APG"),
    ("spg", "SPG"), ("bpg", "BPG"),
]


def leaders_view(world: World, *, top: int = 10) -> dict:
    """League leaders across several categories (generalizes ui.app_ui._league_leaders)."""
    threshold = max(1, world.day // 4)
    qualified = [p for p in world.players.values() if p.season.gp >= threshold]

    def value(p: Player, stat: str) -> float:
        s = p.season
        if stat == "spg":
            return s.per_game("stl")
        if stat == "bpg":
            return s.per_game("blk")
        return getattr(s, stat)

    cats = []
    for stat, label in _LEADER_STATS:
        ranked = sorted(qualified, key=lambda p: value(p, stat), reverse=True)[:top]
        cats.append({
            "stat": stat,
            "label": label,
            "leaders": [{
                "pid": p.pid,
                "name": p.name,
                "team_abbrev": (world.find_team(p.team_id).abbrev if p.team_id is not None
                                and world.find_team(p.team_id) else "FA"),
                "value": round(value(p, stat), 1),
            } for p in ranked],
        })
    return {"categories": cats}


# ---------------------------------------------------------------------------
# Finances (mirrors ui.screens.finances; reuses systems.cap)
# ---------------------------------------------------------------------------
def finances_view(world: World, team: Team) -> dict:
    rows = []
    players = sorted(roster_players(team, world.players),
                     key=lambda p: p.contract.current_salary, reverse=True)
    for p in players:
        market = cap.market_salary(p)
        rows.append({
            "pid": p.pid,
            "name": p.name,
            "position": p.position,
            "age": p.age,
            "overall": p.overall,
            "salary": p.contract.current_salary,
            "years_remaining": p.contract.years_remaining,
            "market_value": market,
            "surplus": market - p.contract.current_salary,
        })
    return {
        "team": team_brief(team),
        "payroll": cap.payroll(world, team),
        "salary_cap": world.salary_cap,
        "cap_space": cap.cap_space(world, team),
        "luxury_tax_line": world.luxury_tax_line,
        "luxury_tax": cap.luxury_tax(world, team),
        "owner_budget": team.owner_budget,
        "contracts": rows,
    }


# ---------------------------------------------------------------------------
# Free agents
# ---------------------------------------------------------------------------
def free_agents_view(world: World) -> dict:
    team = world.user_team
    fas = sorted(world.free_agent_players(), key=lambda p: p.overall, reverse=True)
    rows = []
    for p in fas:
        ask = cap.market_salary(p)
        can_sign, reason = (cap.can_sign(world, team, ask) if team else (False, ""))
        row = player_row(world, p)
        row["ask"] = ask
        row["can_sign"] = can_sign
        row["sign_reason"] = reason
        rows.append(row)
    return {"free_agents": rows}


# ---------------------------------------------------------------------------
# Game results (box score, line score, play-by-play)
# ---------------------------------------------------------------------------
def _box_rows(world: World, result: GameResult, tid: int) -> List[dict]:
    team = world.find_team(tid)
    lines = [(pid, result.box[pid]) for pid in team.roster if pid in result.box]
    lines.sort(key=lambda kv: kv[1].secs, reverse=True)
    rows = []
    for pid, s in lines:
        if s.secs == 0:
            continue
        p = world.players[pid]
        rows.append({
            "pid": pid, "name": p.short_name, "min": round(s.minutes),
            "pts": s.pts, "reb": s.reb, "ast": s.ast, "stl": s.stl, "blk": s.blk,
            "tov": s.tov, "fgm": s.fgm, "fga": s.fga, "tpm": s.tpm, "tpa": s.tpa,
            "ftm": s.ftm, "fta": s.fta, "plus_minus": s.plus_minus,
        })
    return rows


def game_result_view(world: World, result: GameResult) -> dict:
    home = world.find_team(result.home_tid)
    away = world.find_team(result.away_tid)
    return {
        "home": team_brief(home),
        "away": team_brief(away),
        "home_score": result.home_score,
        "away_score": result.away_score,
        "period_label": result.period_label,
        "line_score": [{"home": ls[0], "away": ls[1]} for ls in result.line_score],
        "box": {
            "home": _box_rows(world, result, result.home_tid),
            "away": _box_rows(world, result, result.away_tid),
        },
        "pbp": [{
            "quarter": e.quarter, "clock": e.clock,
            "tid": e.tid, "text": e.text,
            "home_score": e.home_score, "away_score": e.away_score,
        } for e in result.pbp],
    }


def schedule_result(world: World, game) -> dict:
    """A one-line played-game summary (for recent-results lists)."""
    home, away = world.find_team(game.home), world.find_team(game.away)
    return {
        "gid": game.gid, "day": game.day,
        "home": team_brief(home), "away": team_brief(away),
        "home_score": game.home_score, "away_score": game.away_score,
        "played": game.played, "is_playoff": game.is_playoff,
        "winner": game.winner,
    }
