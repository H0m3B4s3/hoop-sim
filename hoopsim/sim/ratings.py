"""Derived lineup ratings and tactic-to-number mappings consumed by the engine.

Keeping this separate from ``engine.py`` means the math that turns five players + a tactic into
modifiers is testable on its own and easy to rebalance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from hoopsim.models.player import Player

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


# ---------------------------------------------------------------------------
# Realization: morale, chemistry, and clutch as one model
# ---------------------------------------------------------------------------
# Momentum (morale), chemistry (lineup familiarity), and clutch all answer the same question:
# how much of a player's ability over the 70 baseline actually *shows up* this trip. Each is a
# factor in [floor, 1.0] that scales the skill *gap* in the shot math (offense and defense alike,
# to preserve the gap-parity that keeps league scoring drift-neutral). The cap is 1.0 by design —
# a player reaches his ceiling when confident, gelled, and ice in his veins, but never exceeds it.
# Neutral anchors at 1.0 so today's tuned scoring is untouched; only slumps, scrambled fives, and
# the rattled-under-pressure dip below.
MORALE_R_MIN = 0.85             # deepest a total funk drags a player below his ceiling
MORALE_R_SLOPE = 0.0024         # realization lost per morale point below neutral
CHEM_R_MIN = 0.92             # a five of strangers vs a fully gelled unit
CLUTCH_R_MIN = 0.93           # worst choke under pressure
CLUTCH_PRESSURE_ANCHOR = 0.97  # realization for an average-clutch player under pressure


def morale_realization(morale: int) -> float:
    """How fully a player realizes his ability given his morale (0..100).

    Neutral (70) and above realize fully (1.0); a slump drags it down toward ``MORALE_R_MIN``.
    Downside-only: high morale never pushes a player past his rating, it just keeps him there.
    """
    return max(MORALE_R_MIN, min(1.0, 1.0 + (morale - 70) * MORALE_R_SLOPE))


def clutch_realization(clutch: int) -> float:
    """Realization under pressure, from a player's clutch rating.

    Clutch is resistance to choking, not a boost: the elite (≈97+) hold their peak (1.0), an
    average player dips a touch (``CLUTCH_PRESSURE_ANCHOR``), and the weak-nerved choke toward
    ``CLUTCH_R_MIN``. Only applied inside the clutch window.
    """
    return max(CLUTCH_R_MIN, min(1.0, CLUTCH_PRESSURE_ANCHOR + (clutch - 70) * 0.0011))


# Shared on-court seconds at which a pair of players is "fully gelled". Rosters that begin a save
# together are seeded to this so an established league plays at full chemistry from tip-off; new
# acquisitions (drafted, signed, traded) start cold and gel as they log minutes together.
FULL_CHEM_SECS = 40_000.0


def familiarity_realization(shared_secs: float) -> float:
    """How fully a lineup realizes its talent given its average shared floor-time.

    Strangers sit at ``CHEM_R_MIN`` (miscommunication, blown coverages, turnovers); a unit that
    has logged ``FULL_CHEM_SECS`` together plays to its full ability (1.0). Linear ramp between.
    """
    frac = max(0.0, min(1.0, shared_secs / FULL_CHEM_SECS))
    return CHEM_R_MIN + (1.0 - CHEM_R_MIN) * frac


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
    # Lineup-level realization factors (see morale_realization / familiarity). ``chem_real`` is the
    # five's familiarity (1.0 until chemistry is wired in); ``avg_morale_real`` is the mean of the
    # five's morale realization, used to scale this lineup's *defensive* skill gap.
    chem_real: float = 1.0
    avg_morale_real: float = 1.0


def _frontcourt_factor(p: Player) -> float:
    return 1.25 if p.position in ("PF", "C") else (1.0 if p.position == "SF" else 0.75)


def build_lineup_cache(players: List[Player], chem_real: float = 1.0) -> LineupCache:
    cache = LineupCache(players=players, chem_real=chem_real)
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
        cache.avg_morale_real = sum(morale_realization(p.morale) for p in players) / n
    return cache
