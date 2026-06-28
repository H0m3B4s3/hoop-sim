"""Head-coach archetypes — a team's rotation identity and tactical lean.

Each team has a :class:`Coach` whose ``archetype`` keys into the :data:`ARCHETYPES` preset table.
A profile drives three things: the team's default tactics (set at generation), how minutes are
shaped across the rotation (``models/team.py`` ``set_auto_minutes``), and how readily the engine
subs tired players (``sim/engine.py`` ``choose_lineup``).

Tendency numbers live in the preset table, *not* in saves, so they can be rebalanced freely. The
``Balanced`` profile reproduces the engine's historical hardcoded values exactly, and a team with
no coach falls back to it — so existing saves behave identically until a real archetype is assigned.

Distinct from :class:`hoopsim.sim.coach.Coach`, which is the live in-game play-caller interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Tuple

if TYPE_CHECKING:                       # avoid a models.team <-> models.coach import cycle
    from hoopsim.models.team import Team


@dataclass(frozen=True)
class CoachProfile:
    """Static tendency knobs for one archetype (looked up, never serialized)."""
    key: str
    label: str
    blurb: str
    weight: float                       # relative frequency when assigning coaches at generation
    # default tactics this archetype leans toward
    pace: str = "Balanced"
    off_focus: str = "Balanced"
    ball_movement: str = "Balanced"
    def_pressure: str = "Balanced"
    # rotation shape (consumed by set_auto_minutes)
    rotation_size: int = 10             # how many players get minutes
    star_reliance: float = 1.40         # exponent on (overall-55); higher piles minutes on stars
    cap_slack: int = 10                 # per-player minute cap = game_minutes - cap_slack
    floor_bonus: int = 0                # starter floor = game_minutes//2 + floor_bonus
    # in-game behavior (consumed by choose_lineup)
    fatigue_weight: float = 22.0        # how hard fatigue pushes a tired player to the bench


# ``Balanced`` is the anchor: its numbers equal the engine's old hardcoded constants so that
# coach=None and coach=Balanced are indistinguishable. Change with care.
BALANCED = CoachProfile(
    key="Balanced", label="Balanced",
    blurb="No strong lean — plays matchups and a standard rotation.",
    weight=34.0,
)

ARCHETYPES: Dict[str, CoachProfile] = {p.key: p for p in [
    BALANCED,
    # --- leans (the common majority) ---------------------------------------
    CoachProfile(
        key="PaceAndSpace", label="Pace & Space",
        blurb="Pushes tempo and spreads the floor with shooters.",
        weight=14.0, pace="Fast", off_focus="Perimeter", ball_movement="Motion",
        rotation_size=10, star_reliance=1.30, cap_slack=10, floor_bonus=0, fatigue_weight=24.0,
    ),
    CoachProfile(
        key="GrindItOut", label="Grind It Out",
        blurb="Slows the game to a crawl and pounds it inside.",
        weight=14.0, pace="Slow", off_focus="Inside", ball_movement="Iso",
        def_pressure="Conservative",
        rotation_size=8, star_reliance=1.50, cap_slack=9, floor_bonus=2, fatigue_weight=18.0,
    ),
    CoachProfile(
        key="DefensiveAnchor", label="Defensive Anchor",
        blurb="Defense first — pressures the ball and walls off the rim.",
        weight=14.0, pace="Slow", off_focus="Inside", def_pressure="Aggressive",
        rotation_size=9, star_reliance=1.40, cap_slack=9, floor_bonus=2, fatigue_weight=20.0,
    ),
    # --- outliers (rare, distinctive) --------------------------------------
    CoachProfile(
        key="SevenSeconds", label="Seven Seconds",
        blurb="Score in seven seconds or less — all gas, little defense.",
        weight=4.0, pace="Fast", off_focus="Perimeter", ball_movement="Motion",
        def_pressure="Conservative",
        rotation_size=9, star_reliance=1.35, cap_slack=8, floor_bonus=2, fatigue_weight=26.0,
    ),
    CoachProfile(
        key="IronRotation", label="Iron Rotation",
        blurb="Rides a tight starting core heavy minutes — injuries be damned.",
        weight=4.0, pace="Slow", ball_movement="Iso", def_pressure="Aggressive",
        rotation_size=7, star_reliance=1.70, cap_slack=4, floor_bonus=6, fatigue_weight=6.0,
    ),
    CoachProfile(
        key="MotionEgalitarian", label="Motion Egalitarian",
        blurb="Shares the ball and the minutes — everybody eats.",
        weight=4.0, ball_movement="Motion",
        rotation_size=10, star_reliance=1.15, cap_slack=12, floor_bonus=0, fatigue_weight=26.0,
    ),
    CoachProfile(
        key="DeepBench", label="Deep Bench",
        blurb="Goes eleven deep to keep legs fresh into the fourth.",
        weight=4.0, rotation_size=11, star_reliance=1.15, cap_slack=12, floor_bonus=0,
        fatigue_weight=28.0,
    ),
]}


@dataclass
class Coach:
    """A team's head coach. The archetype keys into :data:`ARCHETYPES` for its tendencies."""
    name: str = "Coach"
    archetype: str = "Balanced"

    @property
    def profile(self) -> CoachProfile:
        return ARCHETYPES.get(self.archetype, BALANCED)

    def to_dict(self) -> dict:
        return {"name": self.name, "archetype": self.archetype}

    @classmethod
    def from_dict(cls, d: dict) -> "Coach":
        arch = d.get("archetype", "Balanced")
        return cls(name=d.get("name", "Coach"),
                   archetype=arch if arch in ARCHETYPES else "Balanced")


def profile_for(team: "Team") -> CoachProfile:
    """The effective coaching profile for a team — ``Balanced`` when no coach is assigned."""
    coach = getattr(team, "coach", None)
    return coach.profile if coach is not None else BALANCED


def apply_coach_tactics(team: "Team") -> None:
    """Seed a team's default tactics from its coach's archetype lean (called at generation)."""
    prof = profile_for(team)
    team.tactics.pace = prof.pace
    team.tactics.off_focus = prof.off_focus
    team.tactics.ball_movement = prof.ball_movement
    team.tactics.def_pressure = prof.def_pressure


def assign_coach(rng, last_name: str) -> Coach:
    """Pick a weighted-random archetype (outliers rare) and name the coach after ``last_name``."""
    keys: List[str] = list(ARCHETYPES.keys())
    weights: List[float] = [ARCHETYPES[k].weight for k in keys]
    archetype = rng.weighted_one(keys, weights)
    return Coach(name=f"Coach {last_name}", archetype=archetype)


def coach_archetype_labels() -> List[Tuple[str, str]]:
    """(key, label) pairs in table order — handy for UI."""
    return [(p.key, p.label) for p in ARCHETYPES.values()]
