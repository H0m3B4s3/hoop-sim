"""Rating definitions, position weights, and player archetypes.

Ratings live on a 25-99 scale. The engine consumes individual ratings directly; *composites*
and *overall* are derived summaries used for display, AI valuation, and development. Archetypes
shape generation so players have a recognizable identity rather than uniform noise.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from hoopsim.config import RATING_MAX, RATING_MIN

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


# Skews are applied AFTER the overall is calibrated to the target (see playergen), so they carve a
# real identity: large positive deltas are signature elite skills, large negatives are genuine
# holes. Specialists (Rim Protector, Sharpshooter, Post Scorer, Athletic Big, Slasher) are spiky on
# purpose — a Rim Protector should brick threes like Gobert. Balanced roles (Combo Guard, Two-Way,
# Swiss Army Knife) keep gentle skews so they stay well-rounded.
ARCHETYPES: List[Archetype] = [
    Archetype("Floor General", ["PG"],
              {"passing": 16, "off_iq": 12, "ball_handle": 12, "basketball_iq": 12,
               "finishing": -10, "rebounding": -14, "strength": -10, "block": -8},
              (72, 76)),
    Archetype("Scoring Guard", ["PG", "SG"],
              {"three_point": 11, "mid_range": 10, "finishing": 7, "ball_handle": 9,
               "draw_foul": 7, "passing": -8, "perimeter_def": -10, "def_iq": -6},
              (73, 77)),
    Archetype("Combo Guard", ["PG", "SG"],
              {"ball_handle": 7, "passing": 5, "three_point": 5, "mid_range": 4,
               "speed": 5},
              (73, 77)),
    Archetype("3&D Wing", ["SG", "SF"],
              {"three_point": 14, "perimeter_def": 15, "def_iq": 9, "steal": 6,
               "ball_handle": -16, "passing": -13, "off_iq": -8, "draw_foul": -6},
              (77, 81)),
    Archetype("Slasher", ["SG", "SF"],
              {"finishing": 16, "athleticism": 14, "speed": 9, "vertical": 10,
               "draw_foul": 8, "three_point": -24, "free_throw": -12, "off_iq": -6},
              (76, 80)),
    Archetype("Sharpshooter", ["SG", "SF"],
              {"three_point": 20, "mid_range": 11, "free_throw": 13, "off_iq": 4,
               "perimeter_def": -15, "interior_def": -14, "athleticism": -13,
               "strength": -11, "rebounding": -12},
              (76, 80)),
    Archetype("Two-Way Forward", ["SF", "PF"],
              {"perimeter_def": 8, "interior_def": 6, "finishing": 6, "rebounding": 6,
               "def_iq": 7, "basketball_iq": 6},
              (78, 82)),
    Archetype("Stretch Big", ["PF", "C"],
              {"three_point": 16, "mid_range": 9, "finishing": 5, "passing": 4,
               "interior_def": -16, "block": -15, "rebounding": -11, "strength": -8},
              (81, 84)),
    Archetype("Post Scorer", ["PF", "C"],
              {"finishing": 15, "strength": 12, "mid_range": 8, "rebounding": 9,
               "draw_foul": 6, "three_point": -30, "free_throw": -8, "speed": -14,
               "perimeter_def": -12},
              (81, 85)),
    Archetype("Rim Protector", ["C", "PF"],
              {"block": 22, "interior_def": 17, "rebounding": 14, "athleticism": 6,
               "def_iq": 8, "three_point": -38, "mid_range": -22, "free_throw": -16,
               "passing": -12, "ball_handle": -16},
              (82, 86)),
    Archetype("Athletic Big", ["PF", "C"],
              {"athleticism": 14, "vertical": 14, "finishing": 11, "rebounding": 10,
               "block": 8, "free_throw": -16, "three_point": -28, "off_iq": -12,
               "ball_handle": -14, "passing": -8},
              (81, 85)),
    Archetype("Swiss Army Knife", ["SF", "PF", "SG"],
              {"def_iq": 8, "basketball_iq": 7, "consistency": 7, "work_ethic": 8,
               "rebounding": 4, "perimeter_def": 5},
              (77, 81)),
]

ARCHETYPES_BY_POSITION: Dict[str, List[Archetype]] = {pos: [] for pos in POSITIONS}
for _arch in ARCHETYPES:
    for _pos in _arch.positions:
        ARCHETYPES_BY_POSITION[_pos].append(_arch)


# ---------------------------------------------------------------------------
# Rare "unicorn" archetypes — generated only on elite-ceiling players (see
# playergen._choose_archetype) and never in the normal pool, so they stay special.
# ---------------------------------------------------------------------------
# Skews are tuned to sit inside the same overall/scoring envelope as the normal archetypes (see
# the ratings-rebalance work): big signature spikes offset by real holes, so a unicorn is elite at
# his thing without inflating league scoring or his overall above the elite gate.
RARE_ARCHETYPES: List[Archetype] = [
    # Lead creator in a forward's frame (LeBron / Luka / Simmons).
    Archetype("Point Forward", ["SF", "PF"],
              {"passing": 14, "ball_handle": 11, "off_iq": 10, "basketball_iq": 6,
               "finishing": 5, "rebounding": 4, "perimeter_def": 3,
               "three_point": -6, "mid_range": -4, "interior_def": -7, "block": -9,
               "free_throw": -4},
              (79, 82)),
    # Offensive engine at the 5 — elite passing + scoring touch, ground-bound (Jokić; KAT-lite).
    Archetype("Playmaking Big", ["C", "PF"],
              {"passing": 17, "off_iq": 13, "basketball_iq": 8, "mid_range": 8,
               "three_point": 6, "free_throw": 7, "finishing": 5, "rebounding": 5,
               "athleticism": -14, "vertical": -14, "speed": -12, "block": -10,
               "perimeter_def": -9, "interior_def": -6},
              (82, 85)),
    # Athletic two-way force who guards 1–5 with real playmaking, broken jumper (Giannis).
    Archetype("Two-Way Phenom", ["SF", "PF", "C"],
              {"finishing": 12, "athleticism": 12, "vertical": 10, "rebounding": 9,
               "interior_def": 9, "perimeter_def": 6, "block": 7, "def_iq": 6,
               "passing": 6, "ball_handle": 4, "draw_foul": 6,
               "three_point": -26, "free_throw": -16, "mid_range": -12, "off_iq": -6},
              (81, 84)),
    # Elite three-level shotmaker who creates his own look (Durant / Kobe).
    Archetype("Shot Creator", ["SG", "SF"],
              {"three_point": 12, "mid_range": 12, "finishing": 7, "draw_foul": 8,
               "ball_handle": 8, "free_throw": 6, "off_iq": 4,
               "perimeter_def": -14, "def_iq": -10, "interior_def": -10,
               "rebounding": -6, "steal": -6},
              (78, 81)),
]

RARE_ARCHETYPES_BY_POSITION: Dict[str, List[Archetype]] = {pos: [] for pos in POSITIONS}
for _arch in RARE_ARCHETYPES:
    for _pos in _arch.positions:
        RARE_ARCHETYPES_BY_POSITION[_pos].append(_arch)
