"""The league's top end holds steady over decades instead of draining away.

A 20-season audit (seeds 1-5, all-AI, 82 games) found launch rosters held ~75 players at 80+ while
the draft only sustained ~25-30, so the star count fell by two-thirds once the launch cohort
retired. Launch and draft are now tuned to the same level: ~45 at 80+ at launch, ~50 in a settled
league. A full 20-season run is too slow for the suite, so these pin both ends of the pipeline.
"""
from __future__ import annotations

import statistics as st

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.team import roster_players
from hoopsim.systems import draft_system as D

SEEDS = range(1, 7)


def _rostered(world):
    return [p for t in world.team_list() for p in roster_players(t, world.players)]


def test_launch_top_end_matches_what_the_draft_sustains():
    n80, n85, n90, pot80 = [], [], [], []
    for seed in SEEDS:
        players = _rostered(build_world(seed=seed, backstory=False))
        n80.append(sum(p.overall >= 80 for p in players))
        n85.append(sum(p.overall >= 85 for p in players))
        n90.append(sum(p.overall >= 90 for p in players))
        pot80.append(sum(p.potential >= 80 for p in players))
    assert 35 <= st.mean(n80) <= 55, n80
    assert 12 <= st.mean(n85) <= 28, n85
    assert 2 <= st.mean(n90) <= 10, n90        # 90+ stays rare
    # No more unrealized ceiling than a settled league carries (~70-75), or the star count
    # balloons over the first few seasons as the launch youth grow into it.
    assert st.mean(pot80) <= 85, pot80


def test_draft_classes_supply_enough_future_stars():
    w = build_world(seed=1, backstory=False)
    c80, c85, c90 = [], [], []
    for _ in range(40):
        pots = [w.players[pid].potential for pid in D.generate_draft_class(w)]
        c80.append(sum(p >= 80 for p in pots))
        c85.append(sum(p >= 85 for p in pots))
        c90.append(sum(p >= 90 for p in pots))
    # Per class, on average: a handful of future 80s, one or two real stars, a superstar every
    # few years. Below this the league drains; well above it, 90+ stops being rare.
    assert 3.0 <= st.mean(c80) <= 6.0, st.mean(c80)
    assert 1.0 <= st.mean(c85) <= 2.5, st.mean(c85)
    assert 0.2 <= st.mean(c90) <= 0.8, st.mean(c90)
