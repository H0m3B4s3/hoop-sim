"""Derived lineup ratings and tactic-to-number mappings consumed by the engine.

Keeping this separate from ``engine.py`` means the math that turns five players + a tactic into
modifiers is testable on its own and easy to rebalance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from hoopr.models.player import Player

# ---------------------------------------------------------------------------
# Tactic -> numeric modifiers
# ---------------------------------------------------------------------------
PACE_FACTOR = {"Balanced": 1.0, "Slow": 1.13, "Fast": 0.88}   # multiplies seconds/possession

# Offensive focus: (delta to rim tendency, delta to three tendency).
OFF_FOCUS_SHOT = {
    "Balanced": (0.00, 0.00),
    "Inside": (0.10, -0.08),
    "Perimeter": (-0.08, 0.10),
}

# Ball movement: assist propensity delta and usage concentration on the top creator.
BALL_MOVEMENT_ASSIST = {"Balanced": 0.0, "Motion": 0.10, "Iso": -0.18}
BALL_MOVEMENT_CONCENTRATION = {"Balanced": 1.0, "Motion": 0.8, "Iso": 1.6}

# Defensive scheme: (opp three make delta, opp rim make delta, steal delta, foul delta).
DEF_SCHEME = {
    "Man": (0.000, 0.000, 0.000, 0.000),
    "Switch": (-0.010, 0.015, 0.000, 0.005),
    "Zone": (0.015, -0.020, -0.010, -0.010),
}

# Defensive pressure: (steal delta, foul delta, forced-turnover delta, opp rim make delta).
DEF_PRESSURE = {
    "Balanced": (0.000, 0.000, 0.000, 0.000),
    "Conservative": (-0.010, -0.012, -0.015, -0.010),
    "Aggressive": (0.018, 0.018, 0.022, 0.012),
}

# Rebounding focus: offensive-rebound probability delta.
REBOUND_FOCUS_OREB = {"Balanced": 0.0, "Crash Boards": 0.05, "Get Back": -0.05}


@dataclass
class LineupCache:
    """Pre-computed aggregates for a five-player on-court lineup."""
    players: List[Player]
    usage: List[float] = field(default_factory=list)        # shooter selection weights
    passing_w: List[float] = field(default_factory=list)    # assist credit weights
    rebound_w: List[float] = field(default_factory=list)    # rebound credit weights
    foul_w: List[float] = field(default_factory=list)       # who commits fouls
    avg_perimeter_def: float = 70.0
    interior_anchor: float = 70.0                            # best rim deterrent
    block_anchor: float = 70.0
    avg_steal: float = 70.0
    avg_def_iq: float = 70.0
    oreb_power: float = 70.0
    dreb_power: float = 70.0


def _frontcourt_factor(p: Player) -> float:
    return 1.25 if p.position in ("PF", "C") else (1.0 if p.position == "SF" else 0.75)


def build_lineup_cache(players: List[Player]) -> LineupCache:
    cache = LineupCache(players=players)
    for p in players:
        r = p.ratings
        scoring = 0.4 * r["finishing"] + 0.3 * r["three_point"] + 0.3 * r["mid_range"]
        cache.usage.append(max(1.0, scoring + 0.4 * r["ball_handle"] + 0.3 * r["off_iq"] - 60))
        cache.passing_w.append(max(0.5, r["passing"] * 0.7 + r["off_iq"] * 0.3 - 40))
        cache.rebound_w.append(max(0.5, r["rebounding"] * _frontcourt_factor(p)))
        # Bigs and aggressive perimeter players pick up more fouls.
        cache.foul_w.append(max(0.5, 40 + _frontcourt_factor(p) * 20 - 0.2 * r["def_iq"]))

    n = len(players)
    if n:
        cache.avg_perimeter_def = sum(p.ratings["perimeter_def"] for p in players) / n
        cache.avg_steal = sum(p.ratings["steal"] for p in players) / n
        cache.avg_def_iq = sum(p.ratings["def_iq"] for p in players) / n
        cache.interior_anchor = max(
            0.6 * p.ratings["interior_def"] + 0.4 * p.ratings["block"] for p in players)
        cache.block_anchor = max(p.ratings["block"] for p in players)
        cache.oreb_power = sum(p.ratings["rebounding"] * _frontcourt_factor(p)
                               for p in players) / n
        cache.dreb_power = cache.oreb_power
    return cache
