"""Realization model: morale, chemistry, and clutch as one capped factor on the skill gap.

These guard the design invariants — never above 1.0 (no one exceeds his rating), neutral anchors
at exactly 1.0 (today's tuning is untouched), monotonic, and the engine stays league-neutral when
the league sits at neutral morale.
"""
from __future__ import annotations

import statistics as st

from hoopsim.gen.leaguegen import build_world
from hoopsim.sim.engine import simulate_game
from hoopsim.sim.ratings import (
    CHEM_R_MIN, CLUTCH_R_MIN, MORALE_R_MIN,
    build_lineup_cache, clutch_realization, morale_realization,
)


# -- capped at 1.0: reach your ceiling, never beyond -------------------------
def test_realization_never_exceeds_one():
    for m in range(0, 101):
        assert morale_realization(m) <= 1.0
    for c in range(0, 130):
        assert clutch_realization(c) <= 1.0


def test_neutral_realizes_fully():
    # Neutral morale and an average-or-better clutch player both anchor at exactly 1.0 so a
    # content, composed league plays exactly as the engine is tuned today.
    assert morale_realization(70) == 1.0
    assert morale_realization(85) == 1.0      # high morale keeps you at peak, doesn't boost past it
    assert clutch_realization(99) == 1.0


# -- monotonic, and the floors hold ------------------------------------------
def test_morale_monotonic_and_floored():
    vals = [morale_realization(m) for m in range(0, 101)]
    assert all(b >= a for a, b in zip(vals, vals[1:]))     # non-decreasing in morale
    assert vals[0] >= MORALE_R_MIN
    assert morale_realization(40) < 1.0                    # a real slump dips below the ceiling


def test_clutch_monotonic_and_choke():
    vals = [clutch_realization(c) for c in range(0, 100)]
    assert all(b >= a for a, b in zip(vals, vals[1:]))
    assert vals[0] >= CLUTCH_R_MIN
    assert clutch_realization(45) < clutch_realization(70) < 1.0   # the weak-nerved choke


# -- LineupCache carries the lineup-level factors ----------------------------
def test_cache_avg_morale_real_reflects_lineup():
    w = build_world(seed=3)
    team = next(iter(w.teams.values()))
    five = [w.players[pid] for pid in team.roster[:5]]
    for p in five:
        p.morale = 70
    assert abs(build_lineup_cache(five).avg_morale_real - 1.0) < 1e-9
    for p in five:
        p.morale = 30
    assert build_lineup_cache(five).avg_morale_real < 1.0
    # chem defaults to neutral until chemistry is wired in
    assert build_lineup_cache(five).chem_real == 1.0
    assert build_lineup_cache(five, chem_real=0.97).chem_real == 0.97


# -- league neutrality: at neutral morale, scoring stays in the tuned band ----
def _sim_scores(seed, n):
    w = build_world(seed=seed)
    for p in w.players.values():
        p.morale = 70                          # pin the league to neutral
    teams = list(w.teams.values())
    scores = []
    for _ in range(n):
        h, a = w.rng.sample(teams, 2)
        r = simulate_game(w, h, a)
        scores += [r.home_score, r.away_score]
    return scores


def test_neutral_league_scoring_in_band():
    scores = _sim_scores(seed=8, n=200)
    mean = st.mean(scores)
    assert 104 <= mean <= 124, f"neutral-league mean {mean:.1f} drifted out of the tuned band"
