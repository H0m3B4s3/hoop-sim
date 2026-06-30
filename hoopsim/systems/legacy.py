"""Career legacy: accolade tallies, career résumés, milestones, the Hall of Fame, and all-time
leaderboards.

The whole system reads one shared **career ledger** — ``Player.career`` (per-season lines) plus
``Player.accolades`` (an award tally) — so it can't tell whether a season was simulated live or
fabricated at world creation (see ``gen/backstory.py``). A retiree is frozen into a self-contained
*résumé* dict (the same shape for living and retired players), which is what the Hall of Fame and
record book store, so the data survives the player being dropped from ``world.players``.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from hoopsim.models.player import Player
from hoopsim.models.world import World

# -- accolades --------------------------------------------------------------
# Tally keys accrued in offseason.archive_season as each season's awards are crowned.
ACCOLADE_KEYS = ("mvp", "all_league", "dpoy", "roy", "mip", "scoring_title", "champion")
ACCOLADE_LABELS = {
    "mvp": "MVP", "all_league": "All-League", "dpoy": "Defensive POY", "roy": "Rookie of the Year",
    "mip": "Most Improved", "scoring_title": "Scoring Title", "champion": "Champion",
}

# -- Hall of Fame scoring ---------------------------------------------------
# Weighted résumé score; a player clears the bar at HOF_THRESHOLD. Tuned so a multi-time All-League
# / former-MVP-caliber career gets in while a long-tenured role player does not.
ACCOLADE_WEIGHTS = {
    "mvp": 12.0, "all_league": 5.0, "dpoy": 5.0, "scoring_title": 3.0,
    "champion": 3.0, "roy": 2.0, "mip": 1.0,
}
PEAK_ANCHOR = 78            # overall above which peak play starts adding HoF weight
HOF_THRESHOLD = 50.0

# -- milestones -------------------------------------------------------------
# (stat key in totals, human noun, ascending thresholds). Crossed during a season → surfaced in
# the offseason summary ("… joined the 20,000-point club").
MILESTONES = (
    ("pts", "point", (5000, 10000, 15000, 20000, 25000, 30000)),
    ("reb", "rebound", (5000, 10000, 15000)),
    ("ast", "assist", (2500, 5000, 7500, 10000)),
    ("gp", "game", (500, 1000, 1500)),
)


# ---------------------------------------------------------------------------
# Career math
# ---------------------------------------------------------------------------
def career_totals(career: List[dict]) -> Dict[str, float]:
    """Career counting totals + per-game averages, reconstructed from per-season ``career`` lines."""
    gp = sum(e.get("gp", 0) for e in career)
    pts = sum(e.get("gp", 0) * e.get("ppg", 0.0) for e in career)
    reb = sum(e.get("gp", 0) * e.get("rpg", 0.0) for e in career)
    ast = sum(e.get("gp", 0) * e.get("apg", 0.0) for e in career)
    return {
        "gp": int(gp),
        "pts": int(round(pts)), "reb": int(round(reb)), "ast": int(round(ast)),
        "ppg": round(pts / gp, 1) if gp else 0.0,
        "rpg": round(reb / gp, 1) if gp else 0.0,
        "apg": round(ast / gp, 1) if gp else 0.0,
    }


def hof_score(resume: dict) -> float:
    """Weighted Hall-of-Fame score from a résumé's accolades, peak, longevity, and production."""
    acc = resume.get("accolades", {})
    score = sum(ACCOLADE_WEIGHTS.get(k, 0.0) * acc.get(k, 0) for k in ACCOLADE_WEIGHTS)
    score += max(0, resume.get("peak_ovr", 0) - PEAK_ANCHOR) * 2.0
    score += resume.get("seasons", 0) * 1.0
    score += resume.get("totals", {}).get("pts", 0) / 2000.0
    return round(score, 1)


def resume(world: World, player: Player, retired_year: Optional[int] = None) -> dict:
    """A self-contained legacy résumé — works for a living player or a retiree being frozen."""
    career = player.career
    totals = career_totals(career)
    peak_ovr = max([e.get("ovr", 0) for e in career] + [player.overall])
    team = world.find_team(player.team_id)
    last_team = career[-1].get("team") if career else (team.abbrev if team else "FA")
    out = {
        "pid": player.pid,
        "name": player.name,
        "position": player.position,
        "seasons": len(career),
        "peak_ovr": peak_ovr,
        "totals": totals,
        "accolades": {k: v for k, v in player.accolades.items() if v},
        "last_team": last_team,
        "first_year": career[0].get("year") if career else world.season_year,
        "last_year": career[-1].get("year") if career else world.season_year,
        "draft": dict(player.draft) if player.draft else None,
    }
    out["hof_score"] = hof_score(out)
    out["hof"] = out["hof_score"] >= HOF_THRESHOLD
    if retired_year is not None:
        out["retired_year"] = retired_year
        out["induction_year"] = retired_year if out["hof"] else None
    return out


# ---------------------------------------------------------------------------
# Accolade accrual (called from archive_season after awards are computed)
# ---------------------------------------------------------------------------
def _tick(world: World, pid: Optional[int], key: str) -> None:
    p = world.players.get(pid) if pid is not None else None
    if p is not None:
        p.accolades[key] = p.accolades.get(key, 0) + 1


def record_accolades(world: World, awards: dict, champion_tid) -> None:
    """Tick each season-award winner's personal tally so career résumés stay self-contained."""
    if awards.get("mvp"):
        _tick(world, awards["mvp"].get("pid"), "mvp")
    if awards.get("roy"):
        _tick(world, awards["roy"].get("pid"), "roy")
    if awards.get("dpoy"):
        _tick(world, awards["dpoy"].get("pid"), "dpoy")
    if awards.get("mip"):
        _tick(world, awards["mip"].get("pid"), "mip")
    leaders = awards.get("leaders") or {}
    if leaders.get("pts"):
        _tick(world, leaders["pts"].get("pid"), "scoring_title")
    for team_rows in awards.get("all_league", []):
        for row in team_rows:
            _tick(world, row.get("pid"), "all_league")
    champ = world.teams.get(champion_tid) if champion_tid in world.teams else None
    if champ is not None:
        for pid in champ.roster:
            p = world.players.get(pid)
            if p is not None and p.season.gp > 0:
                _tick(world, pid, "champion")


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------
def crossed_milestones(prev: Dict[str, float], now: Dict[str, float]) -> List[dict]:
    """Milestone thresholds a player's career totals crossed between ``prev`` and ``now``."""
    out: List[dict] = []
    for key, noun, thresholds in MILESTONES:
        before, after = prev.get(key, 0), now.get(key, 0)
        for t in thresholds:
            if before < t <= after:
                out.append({"stat": key, "noun": noun, "value": t})
    return out


# ---------------------------------------------------------------------------
# Retirement → résumé snapshot + Hall of Fame
# ---------------------------------------------------------------------------
def retire(world: World, player: Player) -> dict:
    """Freeze a retiring player into a résumé snapshot; induct into the Hall of Fame if worthy.

    Returns the snapshot (with ``hof``/``induction_year`` set) so callers can surface inductees.
    """
    snap = resume(world, player, retired_year=world.season_year)
    world.retired.append(snap)
    if snap["hof"]:
        world.hall_of_fame.append(snap)
    return snap


# ---------------------------------------------------------------------------
# All-time leaderboards (living + retired)
# ---------------------------------------------------------------------------
LEADERBOARD_CATEGORIES = ("pts", "reb", "ast", "gp")


def leaderboards(world: World, category: str = "pts", limit: int = 25) -> List[dict]:
    """Career totals across everyone — current players and retirees — ranked for the record book."""
    rows: List[dict] = []
    seen = set()
    for p in world.players.values():
        if p.career:                                  # only players with completed seasons
            r = resume(world, p)
            r["active"] = True
            rows.append(r)
            seen.add(p.pid)
    for snap in world.retired:
        if snap.get("pid") not in seen:               # a current player can't also be retired
            row = dict(snap)
            row["active"] = False
            rows.append(row)
    rows.sort(key=lambda r: r["totals"].get(category, 0), reverse=True)
    return rows[:limit]
