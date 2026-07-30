"""Assistant coaching staff — specialists a team hires behind the head coach.

The head coach (``models/coach.py``) sets a team's rotation and tactical identity. Assistants are
narrower: each one improves a single thing the front office actually cares about, and each costs
money against ``Team.owner_budget``, so a staff is a budget decision rather than a free upgrade.

Every specialty here deliberately affects **player state between games** — development, injury
risk, conditioning, scouting error — and none of them touch shot probabilities. The engine's
shot math is calibrated with the shooter's and defender's coefficients held symmetric (see
``sim/CLAUDE.md``); a coach who quietly buffed one side of that would drift league-wide scoring,
which is exactly the bug an earlier rebalance was built to kill. Specialists that pay off in
availability and growth are both safer and easier for a player to actually notice.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class StaffRole:
    """Static description of one specialty (looked up by key, never serialized)."""
    key: str
    label: str
    blurb: str


ROLES: Dict[str, StaffRole] = {r.key: r for r in [
    StaffRole("development", "Player Development",
              "Young players improve faster in the offseason."),
    StaffRole("trainer", "Athletic Trainer",
              "Fewer soft-tissue injuries and quicker returns."),
    StaffRole("conditioning", "Strength & Conditioning",
              "Players hold their condition deeper into the season."),
    StaffRole("scout", "Head Scout",
              "Sharper reads on draft prospects — less guesswork on potential."),
]}

ROLE_KEYS: Tuple[str, ...] = tuple(ROLES.keys())

# One hire per specialty; a staff is four slots, not an arms race.
MAX_PER_ROLE = 1

# Grade bands. Level runs 1-5; salary scales steeply so a full elite staff is a real budget
# commitment against owner_budget rather than something every team can simply afford.
LEVEL_LABELS: Dict[int, str] = {1: "Journeyman", 2: "Solid", 3: "Respected",
                                4: "Elite", 5: "Best in the League"}
LEVEL_SALARY: Dict[int, int] = {1: 400_000, 2: 900_000, 3: 1_800_000,
                                4: 3_200_000, 5: 5_000_000}


@dataclass
class Assistant:
    """One hired specialist. ``level`` is 1-5; the effect size scales off it."""
    name: str
    role: str
    level: int = 1

    @property
    def label(self) -> str:
        return ROLES[self.role].label if self.role in ROLES else self.role

    @property
    def level_label(self) -> str:
        return LEVEL_LABELS.get(self.level, "Journeyman")

    @property
    def salary(self) -> int:
        return LEVEL_SALARY.get(self.level, LEVEL_SALARY[1])

    def to_dict(self) -> dict:
        return {"name": self.name, "role": self.role, "level": self.level}

    @classmethod
    def from_dict(cls, d: dict) -> "Assistant":
        role = d.get("role", "development")
        return cls(name=d.get("name", "Assistant"),
                   role=role if role in ROLES else "development",
                   level=max(1, min(5, int(d.get("level", 1)))))


# ---------------------------------------------------------------------------
# Lookups used by the systems that actually apply the effects
# ---------------------------------------------------------------------------
def find(staff: List[Assistant], role: str) -> Optional[Assistant]:
    """The hired specialist for a role, or ``None``."""
    for a in staff:
        if a.role == role:
            return a
    return None


def level_of(staff: List[Assistant], role: str) -> int:
    """Hired level for a role, 0 when the slot is empty. This is the input every effect scales
    off, so an unstaffed team is always the 0 baseline and nothing has to special-case ``None``.
    """
    a = find(staff, role)
    return a.level if a is not None else 0


def staff_cost(staff: List[Assistant]) -> int:
    return sum(a.salary for a in staff)
