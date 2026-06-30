"""Rare 'unicorn' archetypes: generated only for elite-ceiling players, and kept rare."""
from __future__ import annotations

from hoopsim.gen.leaguegen import build_world
from hoopsim.gen.playergen import ELITE_CEILING, make_player
from hoopsim.gen.namegen import NameGenerator
from hoopsim.models.attributes import RARE_ARCHETYPES, ARCHETYPES
from hoopsim.rng import Rng

RARE_NAMES = {a.name for a in RARE_ARCHETYPES}


def test_rare_archetypes_are_separate_from_the_normal_pool():
    normal = {a.name for a in ARCHETYPES}
    assert RARE_NAMES.isdisjoint(normal)
    assert RARE_NAMES == {"Point Forward", "Playmaking Big", "Two-Way Phenom", "Shot Creator"}


def test_low_target_players_never_get_a_unicorn():
    rng = Rng(1)
    names = NameGenerator(rng)
    for _ in range(400):
        p = make_player(rng, 1, names, target_overall=68, age=27)  # below the elite gate
        assert p.archetype not in RARE_NAMES


def test_elite_players_sometimes_get_a_unicorn():
    rng = Rng(2)
    names = NameGenerator(rng)
    got = sum(1 for _ in range(400)
              if make_player(rng, 1, names, target_overall=90, age=25).archetype in RARE_NAMES)
    assert got > 0                       # elites can roll a unicorn
    assert got < 400                     # but not always — normal elite archetypes still appear


def test_unicorns_appear_but_stay_rare_in_a_league():
    w = build_world(seed=1, backstory=False)
    rare = [p for p in w.players.values() if p.archetype in RARE_NAMES]
    share = len(rare) / len(w.players)
    assert rare, "expected at least a few unicorns in a league"
    assert share < 0.10, f"unicorns should be rare, got {share:.0%}"
    # every unicorn is genuinely elite-caliber (a star or a high-ceiling youngster), never a role
    # player — the gate is optimistic, so realized overall/potential can land just under it
    assert all(p.overall >= 78 or p.potential >= ELITE_CEILING for p in rare)


def test_overall_not_inflated_by_rare_archetypes():
    """A unicorn calibrated to a target lands near it — the skews don't balloon the overall."""
    rng = Rng(7)
    names = NameGenerator(rng)
    rares = []
    while len(rares) < 30:
        p = make_player(rng, 1, names, target_overall=88, age=24)
        if p.archetype in RARE_NAMES:
            rares.append(p)
    # within a few points of target on average (skews are spike-and-hole, not net buffs)
    avg = sum(p.overall for p in rares) / len(rares)
    assert 85 <= avg <= 92
