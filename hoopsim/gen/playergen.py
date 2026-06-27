"""Procedural player generation.

Players are built around an archetype for a recognizable identity, then nudged to hit a target
overall via an additive shift (exact pre-clamp, since the overall is a convex combination of
ratings). Potential is a function of age so young players carry upside and veterans don't.
"""
from __future__ import annotations

from typing import List, Optional

from hoopsim.config import RATING_MAX, RATING_MIN, ROOKIE_AGE_RANGE
from hoopsim.models.attributes import (ALL_RATINGS, ARCHETYPES_BY_POSITION, POSITIONS,
                                     clamp_rating, overall)
from hoopsim.models.player import Player
from hoopsim.gen.namegen import NameGenerator
from hoopsim.rng import Rng

_MARKETABILITY = {"marketability", "charisma"}
SKILL_RATINGS: List[str] = [r for r in ALL_RATINGS if r not in _MARKETABILITY]

# Wings are slightly more common than guards/bigs, mirroring real rosters.
_POSITION_WEIGHTS = {"PG": 0.20, "SG": 0.22, "SF": 0.22, "PF": 0.20, "C": 0.16}


def _pick_position(rng: Rng) -> str:
    return rng.weighted_one(POSITIONS, [_POSITION_WEIGHTS[p] for p in POSITIONS])


def _secondary_position(rng: Rng, primary: str) -> Optional[str]:
    idx = POSITIONS.index(primary)
    neighbors = []
    if idx > 0:
        neighbors.append(POSITIONS[idx - 1])
    if idx < len(POSITIONS) - 1:
        neighbors.append(POSITIONS[idx + 1])
    if neighbors and rng.chance(0.55):
        return rng.choice(neighbors)
    return None


def _potential(rng: Rng, ovr: int, age: int) -> int:
    if age >= 29:
        return int(min(RATING_MAX, ovr + rng.randint(0, 1)))
    mu = max(0.0, (27 - age) * 1.8)
    upside = max(0.0, rng.gauss(mu, mu * 0.6 + 2.0))
    return int(min(RATING_MAX, round(ovr + upside)))


def _weight_for(rng: Rng, height_in: int, strength: int) -> int:
    base = height_in * 2.55 + (strength - 60) * 0.5
    return int(max(160, min(290, base + rng.uniform(-10.0, 16.0))))


def make_player(rng: Rng, pid: int, names: NameGenerator, *,
                position: Optional[str] = None,
                target_overall: Optional[int] = None,
                age: Optional[int] = None,
                is_prospect: bool = False) -> Player:
    position = position or _pick_position(rng)
    archetype = rng.choice(ARCHETYPES_BY_POSITION[position])

    if age is None:
        age = (rng.randint(*ROOKIE_AGE_RANGE) if is_prospect
               else int(min(36, max(19, round(rng.triangular(19, 36, 26))))))
    if target_overall is None:
        target_overall = int(min(92, max(58, round(rng.gauss(72, 8)))))

    # Base ratings around the target, then carve out the archetype identity.
    ratings = {r: clamp_rating(rng.gauss(target_overall, 7.0)) for r in SKILL_RATINGS}
    for key, delta in archetype.skews.items():
        if key in ratings:
            ratings[key] = clamp_rating(ratings[key] + delta)

    # Additive correction to hit the target overall (exact before clamping).
    current = overall(ratings, position)
    shift = target_overall - current
    if shift:
        for r in SKILL_RATINGS:
            ratings[r] = clamp_rating(ratings[r] + shift)

    # Marketability group is dormant in Phase 1 but populated so saves stay stable.
    ratings["marketability"] = rng.randint(RATING_MIN, 85)
    ratings["charisma"] = rng.randint(RATING_MIN, 85)

    final_ovr = overall(ratings, position)
    height_in = rng.randint(*archetype.height_in)
    weight_lb = _weight_for(rng, height_in, ratings["strength"])
    first, last = names.name()

    experience = 0 if is_prospect else max(0, age - 19 - rng.randint(0, 1))

    return Player(
        pid=pid,
        first_name=first,
        last_name=last,
        age=age,
        position=position,
        archetype=archetype.name,
        height_in=height_in,
        weight_lb=weight_lb,
        ratings=ratings,
        potential=_potential(rng, final_ovr, age),
        secondary_position=_secondary_position(rng, position),
        jersey=rng.randint(0, 55),
        experience=experience,
        condition=100.0,
        morale=rng.randint(60, 85),
        brand_value=ratings["marketability"] * 1000,   # dormant flavor value
        scout_error=rng.randint(-6, 6),
    )
