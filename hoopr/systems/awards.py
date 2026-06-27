"""End-of-season awards, computed from regular-season production and team success.

Run once per season from :func:`hoopr.systems.offseason.archive_season`, *before* the season's
stats roll into career history — so rookies still have an empty ``career`` and most-improved can
compare against last year's overall. Results are stored as plain dicts on ``world.history`` and
are self-contained (name/team/stat snapshots), so they survive players later retiring.
"""
from __future__ import annotations

from typing import List, Optional

from hoopr.models.attributes import composite
from hoopr.models.player import Player
from hoopr.models.world import World

MIN_GP_FRACTION = 0.55       # games needed for MVP / All-League / DPOY eligibility
ROOKIE_GP_FRACTION = 0.40    # rookies and MIP get a lower bar
MIP_MIN_JUMP = 3             # overall must climb at least this much to be "most improved"


def _value(p: Player, team_win_pct: float) -> float:
    """A simple all-in-one production score, nudged by efficiency and team success."""
    s = p.season
    if s.gp == 0:
        return 0.0
    prod = (s.ppg + 1.2 * s.rpg + 1.5 * s.apg
            + 2.0 * s.per_game("stl") + 2.0 * s.per_game("blk") - s.per_game("tov"))
    efficiency = 0.6 + 0.4 * (s.ts_pct / 0.55)        # ~0.55 TS% is league-neutral
    return prod * efficiency * (0.7 + 0.3 * team_win_pct)


def _entry(world: World, p: Player, **extra) -> dict:
    """A self-contained award snapshot (frozen name/team/stats plus a live tid for coloring)."""
    team = world.find_team(p.team_id)
    s = p.season
    out = {
        "pid": p.pid,
        "name": p.name,
        "tid": p.team_id,
        "team": team.abbrev if team else "FA",
        "position": p.position,
        "overall": p.overall,
        "ppg": round(s.ppg, 1),
        "rpg": round(s.rpg, 1),
        "apg": round(s.apg, 1),
        "spg": round(s.per_game("stl"), 1),
        "bpg": round(s.per_game("blk"), 1),
    }
    out.update(extra)
    return out


def compute_awards(world: World) -> dict:
    """Pick the season's award winners from current (not-yet-archived) season stats."""
    games = max(1, world.season_games)
    min_gp = games * MIN_GP_FRACTION
    rookie_gp = games * ROOKIE_GP_FRACTION
    wp = {t.tid: t.win_pct for t in world.team_list()}
    # Source candidates from the user league's rosters only — never the pipeline-partner
    # league — so a background-league player can never surface as a winner.
    rostered = [p for t in world.team_list() for pid in t.roster
                if pid in world.players and (p := world.players[pid]).season.gp > 0]

    def val(p: Player) -> float:
        return _value(p, wp.get(p.team_id, 0.0))

    eligible = sorted((p for p in rostered if p.season.gp >= min_gp), key=val, reverse=True)
    awards: dict = {}

    if eligible:
        awards["mvp"] = _entry(world, eligible[0])
        all_league = [[_entry(world, p) for p in eligible[i:i + 5]]
                      for i in range(0, min(15, len(eligible)), 5)]
        awards["all_league"] = all_league

    rookies = [p for p in rostered if not p.career and p.season.gp >= rookie_gp]
    if rookies:
        awards["roy"] = _entry(world, max(rookies, key=val))

    def dpoy_score(p: Player) -> float:
        s = p.season
        return (composite(p.ratings, "defense")
                + 9 * s.per_game("stl") + 9 * s.per_game("blk") + 1.5 * s.rpg)

    if eligible:
        awards["dpoy"] = _entry(world, max(eligible, key=dpoy_score))

    def improvement(p: Player) -> int:
        prev = p.career[-1].get("ovr") if p.career else None
        return (p.overall - prev) if prev is not None else -999

    improvers = [p for p in rostered if p.career and p.season.gp >= rookie_gp]
    if improvers:
        best = max(improvers, key=improvement)
        if improvement(best) >= MIP_MIN_JUMP:
            awards["mip"] = _entry(world, best, improvement=improvement(best))

    if eligible:
        awards["leaders"] = {
            "pts": _entry(world, max(eligible, key=lambda p: p.season.ppg)),
            "reb": _entry(world, max(eligible, key=lambda p: p.season.rpg)),
            "ast": _entry(world, max(eligible, key=lambda p: p.season.apg)),
        }
    return awards
