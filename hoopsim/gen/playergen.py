"""Procedural player generation.

Players are built around an archetype for a recognizable identity, then nudged to hit a target
overall via an additive shift (exact pre-clamp, since the overall is a convex combination of
ratings). Potential is a function of age so young players carry upside and veterans don't.
"""
from __future__ import annotations

from typing import List, Optional

from hoopsim.config import RATING_MAX, RATING_MIN, ROOKIE_AGE_RANGE
from hoopsim.models.attributes import (ALL_RATINGS, ARCHETYPES_BY_POSITION, POSITIONS,
                                     RARE_ARCHETYPES_BY_POSITION, clamp_rating, overall)
from hoopsim.models.player import Player
from hoopsim.gen.namegen import NameGenerator
from hoopsim.rng import Rng

_MARKETABILITY = {"marketability", "charisma"}
SKILL_RATINGS: List[str] = [r for r in ALL_RATINGS if r not in _MARKETABILITY]

# Wings are slightly more common than guards/bigs, mirroring real rosters.
_POSITION_WEIGHTS = {"PG": 0.20, "SG": 0.22, "SF": 0.22, "PF": 0.20, "C": 0.16}


def _pick_position(rng: Rng) -> str:
    return rng.weighted_one(POSITIONS, [_POSITION_WEIGHTS[p] for p in POSITIONS])


# ``ROOKIE_AGE_RANGE`` (19-23) is a flat draw across those five ages; the modern draft skews much
# younger — one-and-done and international entries make 19-20 the bulk of a class, with each extra
# year of college pulling a shrinking slice.
_DRAFT_AGE_WEIGHTS = {19: 0.32, 20: 0.30, 21: 0.20, 22: 0.12, 23: 0.06}


def draft_age(rng: Rng) -> int:
    ages = list(_DRAFT_AGE_WEIGHTS)
    return rng.weighted_one(ages, [_DRAFT_AGE_WEIGHTS[a] for a in ages])


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


# Rare "unicorn" archetypes are gated to elite-ceiling players so they stay special. The gate uses
# a quick ceiling estimate (target overall plus expected youth growth), and even then only fires on
# a roll — so a league has a handful of unicorns, mostly among its young stars and top prospects.
ELITE_CEILING = 84
RARE_ARCHETYPE_CHANCE = 0.40


def _ceiling_estimate(target_overall: int, age: int) -> int:
    """Rough talent ceiling for archetype gating: current target plus expected growth if young."""
    if age >= 27:
        return target_overall
    return min(99, target_overall + int(round((27 - age) * 1.1)))


def _choose_archetype(rng: Rng, position: str, target_overall: int, age: int):
    """Pick a generation archetype: usually from the normal pool, rarely a unicorn for elite talent."""
    rare = RARE_ARCHETYPES_BY_POSITION.get(position, [])
    if (rare and _ceiling_estimate(target_overall, age) >= ELITE_CEILING
            and rng.chance(RARE_ARCHETYPE_CHANCE)):
        return rng.choice(rare)
    return rng.choice(ARCHETYPES_BY_POSITION[position])


# Potential is squeezed above a soft ceiling so 90+ is uncommon and the far tail (96-99) is a
# career-defining rarity. Shared by every generation path (initial rosters, draft classes) so no
# one pool systematically out-produces another.
_POT_SOFT_CAP = 90
_POT_ELITE_CAP = 95


def _cap_potential(rng: Rng, raw: int) -> int:
    if raw <= _POT_SOFT_CAP:
        return raw
    if not rng.chance(0.20):                        # most rolls above the soft cap get reined in
        return _POT_SOFT_CAP
    if raw <= _POT_ELITE_CAP or not rng.chance(0.15):
        return min(raw, _POT_ELITE_CAP)
    if not rng.chance(0.10):                         # 96-98: a handful of generational prospects
        return min(raw, rng.randint(96, 98))
    return RATING_MAX                                 # 99: roughly a once-a-decade prospect


def _potential(rng: Rng, ovr: int, age: int) -> int:
    if age >= 29:
        raw = int(min(RATING_MAX, ovr + rng.randint(0, 1)))
    else:
        mu = max(0.0, (27 - age) * 1.8)
        upside = max(0.0, rng.gauss(mu, mu * 0.6 + 2.0))
        raw = int(round(ovr + upside))
    # The squeeze can pull an already-high current overall below itself; potential must never
    # trail current ability.
    return max(ovr, _cap_potential(rng, raw))


def _weight_for(rng: Rng, height_in: int, strength: int) -> int:
    base = height_in * 2.55 + (strength - 60) * 0.5
    return int(max(160, min(290, base + rng.uniform(-10.0, 16.0))))


def make_player(rng: Rng, pid: int, names: NameGenerator, *,
                position: Optional[str] = None,
                target_overall: Optional[int] = None,
                age: Optional[int] = None,
                is_prospect: bool = False) -> Player:
    position = position or _pick_position(rng)

    if age is None:
        age = (rng.randint(*ROOKIE_AGE_RANGE) if is_prospect
               else int(min(36, max(19, round(rng.triangular(19, 36, 26))))))
    if target_overall is None:
        # Mean sits at 70 — the engine's league-average anchor — so a freshly generated league
        # scores at target PPP. The 90 cap keeps the very top end scarce; stars are earned through
        # development, not handed out at generation.
        target_overall = int(min(90, max(55, round(rng.gauss(70, 8)))))
    # Archetype is chosen after talent is known so rare unicorn archetypes can be gated to elites.
    archetype = _choose_archetype(rng, position, target_overall, age)

    # Build a bland player and calibrate him to the target overall FIRST, then carve out the
    # archetype identity. Skewing after the calibration shift keeps signature spikes spiked and
    # weaknesses deep — a Rim Protector's jumper or a Sharpshooter's defense survives instead of
    # being averaged back toward the target. The overall is allowed to drift a few points from the
    # target as a result: a one-dimensional specialist is genuinely worth less than his peak skill.
    ratings = {r: clamp_rating(rng.gauss(target_overall, 7.0)) for r in SKILL_RATINGS}
    current = overall(ratings, position)
    shift = target_overall - current
    if shift:
        for r in SKILL_RATINGS:
            ratings[r] = clamp_rating(ratings[r] + shift)
    for key, delta in archetype.skews.items():
        if key in ratings:
            ratings[key] = clamp_rating(ratings[key] + delta)

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
