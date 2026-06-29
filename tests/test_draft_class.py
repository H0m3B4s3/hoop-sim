"""Draft-class talent-shape tests: a couple of stars most years, with deep/weak tails."""
from __future__ import annotations

from hoopsim.gen.leaguegen import build_world
from hoopsim.systems import draft_system as D

STAR_POT = 82   # "real top player" threshold


def _class_top_pots(seed):
    w = build_world(seed=seed)
    w.user_team_id = 1
    ids = D.generate_draft_class(w)
    return [w.players[pid].scouted_potential() for pid in ids]


def test_top_prospect_is_a_plausible_ceiling():
    for seed in range(20):
        pots = _class_top_pots(seed)
        assert 70 <= pots[0] <= 99
        # The board is sorted best-first by scouted talent.
        assert pots[0] >= pots[10]


def test_classes_vary_in_strength_and_depth():
    star_counts = []
    top_pots = []
    for seed in range(60):
        pots = _class_top_pots(seed)
        star_counts.append(sum(1 for p in pots if p >= STAR_POT))
        top_pots.append(pots[0])
    avg_stars = sum(star_counts) / len(star_counts)
    # Most drafts hand out only a small handful of genuine top players...
    assert 0.5 <= avg_stars <= 4.5, avg_stars
    # ...but the class-to-class spread is real: some loaded, some thin.
    assert max(star_counts) - min(star_counts) >= 3
    assert min(star_counts) <= 1               # at least one weak class in the sample
    assert max(star_counts) >= 4               # at least one deep class
    # And some years the #1 pick simply isn't a star.
    assert min(top_pots) < STAR_POT


def test_not_every_prospect_is_high_upside():
    """Guard against the old inflation: the back half should be mostly role-player ceilings."""
    pots = _class_top_pots(7)
    back_half = pots[len(pots) // 2:]
    assert sum(1 for p in back_half if p >= STAR_POT) <= 2
    assert max(back_half) < 90
