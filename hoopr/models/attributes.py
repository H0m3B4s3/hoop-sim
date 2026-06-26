"""Rating definitions, position weights, and player archetypes.

Ratings live on a 25-99 scale. The engine consumes individual ratings directly; *composites*
and *overall* are derived summaries used for display, AI valuation, and development. Archetypes
shape generation so players have a recognizable identity rather than uniform noise.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from hoopr.config import RATING_MAX, RATING_MIN

POSITIONS: Tuple[str, ...] = ("PG", "SG", "SF", "PF", "C")

# Ratings grouped for display. Order within a group is the display order.
RATING_GROUPS: Dict[str, List[str]] = {
    "Physical": ["athleticism", "speed", "strength", "vertical", "stamina", "durability"],
    "Offense": ["finishing", "mid_range", "three_point", "free_throw", "ball_handle",
                "passing", "off_iq", "draw_foul"],
    "Defense": ["perimeter_def", "interior_def", "steal", "block", "def_iq", "rebounding"],
    "Mental": ["consistency", "clutch", "work_ethic", "basketball_iq", "leadership"],
    # Dormant in Phase 1 — drives NIL/recruiting in later phases.
    "Marketability": ["marketability", "charisma"],
}

ALL_RATINGS: List[str] = [r for group in RATING_GROUPS.values() for r in group]

# Composites are intermediate skill axes the overall is built from.
COMPOSITES: Tuple[str, ...] = (
    "scoring", "playmaking", "rebounding", "defense", "athleticism", "intangibles",
)

# How each composite is assembled from raw ratings (weights need not sum to 1; normalized).
_COMPOSITE_FORMULA: Dict[str, Dict[str, float]] = {
    "scoring": {"finishing": 0.30, "mid_range": 0.20, "three_point": 0.30,
                "free_throw": 0.10, "draw_foul": 0.10},
    "playmaking": {"ball_handle": 0.35, "passing": 0.40, "off_iq": 0.25},
    "rebounding": {"rebounding": 1.0},
    "defense": {"perimeter_def": 0.28, "interior_def": 0.28, "steal": 0.15,
                "block": 0.14, "def_iq": 0.15},
    "athleticism": {"athleticism": 0.40, "speed": 0.25, "vertical": 0.20, "strength": 0.15},
    "intangibles": {"basketball_iq": 0.40, "consistency": 0.30, "work_ethic": 0.15,
                    "clutch": 0.15},
}

# Per-position weighting of composites into the overall rating (each row sums to 1.0).
POSITION_WEIGHTS: Dict[str, Dict[str, float]] = {
    "PG": {"scoring": 0.25, "playmaking": 0.30, "rebounding": 0.05,
           "defense": 0.18, "athleticism": 0.12, "intangibles": 0.10},
    "SG": {"scoring": 0.32, "playmaking": 0.15, "rebounding": 0.07,
           "defense": 0.18, "athleticism": 0.18, "intangibles": 0.10},
    "SF": {"scoring": 0.27, "playmaking": 0.13, "rebounding": 0.12,
           "defense": 0.22, "athleticism": 0.16, "intangibles": 0.10},
    "PF": {"scoring": 0.24, "playmaking": 0.08, "rebounding": 0.22,
           "defense": 0.24, "athleticism": 0.12, "intangibles": 0.10},
    "C": {"scoring": 0.22, "playmaking": 0.05, "rebounding": 0.26,
          "defense": 0.27, "athleticism": 0.10, "intangibles": 0.10},
}


def clamp_rating(value: float) -> int:
    """Round and clamp a rating to the legal [RATING_MIN, RATING_MAX] range."""
    return int(max(RATING_MIN, min(RATING_MAX, round(value))))


def composite(ratings: Dict[str, int], name: str) -> float:
    """Compute a single composite axis from raw ratings."""
    formula = _COMPOSITE_FORMULA[name]
    total = sum(formula.values())
    return sum(ratings.get(k, RATING_MIN) * w for k, w in formula.items()) / total


def all_composites(ratings: Dict[str, int]) -> Dict[str, float]:
    return {name: composite(ratings, name) for name in COMPOSITES}


def overall(ratings: Dict[str, int], position: str) -> int:
    """Position-weighted overall rating (25-99)."""
    weights = POSITION_WEIGHTS[position]
    comps = all_composites(ratings)
    value = sum(comps[name] * w for name, w in weights.items())
    return clamp_rating(value)


# ---------------------------------------------------------------------------
# Archetypes — generation templates. ``skews`` are additive deltas applied to a
# player's base ratings to carve out an identity.
# ---------------------------------------------------------------------------
class Archetype:
    __slots__ = ("name", "positions", "skews", "height_in")

    def __init__(self, name: str, positions: List[str], skews: Dict[str, int],
                 height_in: Tuple[int, int]) -> None:
        self.name = name
        self.positions = positions
        self.skews = skews
        self.height_in = height_in  # (min, max) inches, typical for the archetype


ARCHETYPES: List[Archetype] = [
    Archetype("Floor General", ["PG"],
              {"passing": 12, "off_iq": 10, "ball_handle": 10, "basketball_iq": 10,
               "three_point": 3, "finishing": -4, "rebounding": -6},
              (72, 76)),
    Archetype("Scoring Guard", ["PG", "SG"],
              {"three_point": 9, "mid_range": 8, "finishing": 6, "ball_handle": 8,
               "draw_foul": 6, "passing": -4, "perimeter_def": -3},
              (73, 77)),
    Archetype("Combo Guard", ["PG", "SG"],
              {"ball_handle": 7, "passing": 5, "three_point": 5, "mid_range": 4,
               "speed": 5},
              (73, 77)),
    Archetype("3&D Wing", ["SG", "SF"],
              {"three_point": 9, "perimeter_def": 11, "def_iq": 8, "steal": 5,
               "ball_handle": -5, "passing": -4},
              (77, 81)),
    Archetype("Slasher", ["SG", "SF"],
              {"finishing": 11, "athleticism": 10, "speed": 8, "vertical": 8,
               "draw_foul": 7, "three_point": -7, "free_throw": -4},
              (76, 80)),
    Archetype("Sharpshooter", ["SG", "SF"],
              {"three_point": 13, "mid_range": 9, "free_throw": 9, "off_iq": 4,
               "perimeter_def": -5, "athleticism": -5, "rebounding": -4},
              (76, 80)),
    Archetype("Two-Way Forward", ["SF", "PF"],
              {"perimeter_def": 8, "interior_def": 6, "finishing": 6, "rebounding": 6,
               "def_iq": 7, "basketball_iq": 6},
              (78, 82)),
    Archetype("Stretch Big", ["PF", "C"],
              {"three_point": 12, "mid_range": 8, "finishing": 5, "passing": 4,
               "interior_def": -6, "block": -5, "rebounding": -3},
              (81, 84)),
    Archetype("Post Scorer", ["PF", "C"],
              {"finishing": 11, "strength": 9, "mid_range": 7, "rebounding": 8,
               "draw_foul": 5, "three_point": -10, "speed": -6},
              (81, 85)),
    Archetype("Rim Protector", ["C", "PF"],
              {"block": 14, "interior_def": 12, "rebounding": 11, "athleticism": 6,
               "def_iq": 7, "three_point": -12, "passing": -5, "ball_handle": -6},
              (82, 86)),
    Archetype("Athletic Big", ["PF", "C"],
              {"athleticism": 11, "vertical": 11, "finishing": 9, "rebounding": 9,
               "block": 7, "free_throw": -7, "three_point": -9, "off_iq": -4},
              (81, 85)),
    Archetype("Glue Guy", ["SF", "PF", "SG"],
              {"def_iq": 8, "basketball_iq": 7, "consistency": 7, "work_ethic": 8,
               "rebounding": 4, "perimeter_def": 5},
              (77, 81)),
]

ARCHETYPES_BY_POSITION: Dict[str, List[Archetype]] = {pos: [] for pos in POSITIONS}
for _arch in ARCHETYPES:
    for _pos in _arch.positions:
        ARCHETYPES_BY_POSITION[_pos].append(_arch)
