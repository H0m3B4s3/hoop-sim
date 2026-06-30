"""Team-selection strength: stars track projected roster talent, not a flat default."""
from __future__ import annotations

from collections import Counter

from hoopsim.gen.leaguegen import build_world
from hoopsim.sim import power
from hoopsim.web import serializers as ser


def test_strength_stars_spread_across_the_league():
    w = build_world(seed=1)
    stars = power.strength_stars(w)
    counts = Counter(stars.values())
    assert set(counts) <= {1, 2, 3, 4, 5}
    assert min(counts) <= 2 and max(counts) >= 1     # genuine spread, not all one bucket
    assert len(counts) >= 4                           # at least four distinct tiers appear


def test_stronger_roster_earns_more_stars():
    w = build_world(seed=2)
    strength = power.projected_strength(w)
    stars = power.strength_stars(w)
    strongest = max(strength, key=strength.get)
    weakest = min(strength, key=strength.get)
    assert stars[strongest] >= stars[weakest]
    assert stars[strongest] == 5 and stars[weakest] == 1


def test_summary_exposes_team_strength():
    w = build_world(seed=3)
    summary = ser.world_summary(w)
    for t in summary["teams"]:
        assert 1 <= t["strength_stars"] <= 5
        assert t["strength"] > 0
    # not every team is the same — the old bug showed all teams identical
    assert len({t["strength_stars"] for t in summary["teams"]}) > 1
