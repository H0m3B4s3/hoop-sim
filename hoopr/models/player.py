"""The Player model — the central entity of the game."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from hoopr.models.attributes import ALL_RATINGS, overall
from hoopr.models.contract import Contract
from hoopr.models.stats import StatLine


@dataclass
class Injury:
    description: str
    games_remaining: int
    severity: str = "minor"   # minor | moderate | major

    def to_dict(self) -> dict:
        return {"description": self.description, "games_remaining": self.games_remaining,
                "severity": self.severity}

    @classmethod
    def from_dict(cls, d: dict) -> "Injury":
        return cls(d["description"], d["games_remaining"], d.get("severity", "minor"))


@dataclass
class Player:
    pid: int
    first_name: str
    last_name: str
    age: int
    position: str
    archetype: str
    height_in: int
    weight_lb: int
    ratings: Dict[str, int]
    potential: int                       # overall ceiling
    secondary_position: Optional[str] = None
    jersey: int = 0
    team_id: Optional[int] = None
    experience: int = 0                  # completed pro seasons
    contract: Contract = field(default_factory=Contract)

    condition: float = 100.0             # 0-100 between-game freshness (100 = fully rested)
    morale: int = 70                     # 0-100
    injury: Optional[Injury] = None

    # Brand/marketability (dormant in Phase 1; used by NIL phase).
    brand_value: int = 0

    # Hidden: scouting uncertainty on potential (set at generation, never shown raw).
    scout_error: int = 0

    season: StatLine = field(default_factory=StatLine)
    playoffs: StatLine = field(default_factory=StatLine)
    career: List[dict] = field(default_factory=list)   # one summary dict per finished season

    # -- identity -----------------------------------------------------------
    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def short_name(self) -> str:
        return f"{self.first_name[0]}. {self.last_name}"

    @property
    def overall(self) -> int:
        return overall(self.ratings, self.position)

    @property
    def is_free_agent(self) -> bool:
        return self.team_id is None

    @property
    def is_injured(self) -> bool:
        return self.injury is not None and self.injury.games_remaining > 0

    @property
    def available(self) -> bool:
        return not self.is_injured

    @property
    def height_str(self) -> str:
        return f"{self.height_in // 12}-{self.height_in % 12}"

    def rating(self, key: str) -> int:
        return self.ratings.get(key, 25)

    # -- scouting -----------------------------------------------------------
    def scouted_potential(self) -> int:
        """Potential as a scout would estimate it (fuzzed by hidden scout_error)."""
        return max(self.overall, min(99, self.potential + self.scout_error))

    # -- serialization ------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "pid": self.pid,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "age": self.age,
            "position": self.position,
            "secondary_position": self.secondary_position,
            "archetype": self.archetype,
            "height_in": self.height_in,
            "weight_lb": self.weight_lb,
            "jersey": self.jersey,
            "ratings": dict(self.ratings),
            "potential": self.potential,
            "team_id": self.team_id,
            "experience": self.experience,
            "contract": self.contract.to_dict(),
            "condition": self.condition,
            "morale": self.morale,
            "injury": self.injury.to_dict() if self.injury else None,
            "brand_value": self.brand_value,
            "scout_error": self.scout_error,
            "season": self.season.to_dict(),
            "playoffs": self.playoffs.to_dict(),
            "career": list(self.career),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Player":
        ratings = {k: int(d["ratings"].get(k, 25)) for k in ALL_RATINGS}
        return cls(
            pid=d["pid"],
            first_name=d["first_name"],
            last_name=d["last_name"],
            age=d["age"],
            position=d["position"],
            archetype=d["archetype"],
            height_in=d["height_in"],
            weight_lb=d["weight_lb"],
            ratings=ratings,
            potential=d["potential"],
            secondary_position=d.get("secondary_position"),
            jersey=d.get("jersey", 0),
            team_id=d.get("team_id"),
            experience=d.get("experience", 0),
            contract=Contract.from_dict(d.get("contract", {})),
            condition=d.get("condition", 100.0),
            morale=d.get("morale", 70),
            injury=Injury.from_dict(d["injury"]) if d.get("injury") else None,
            brand_value=d.get("brand_value", 0),
            scout_error=d.get("scout_error", 0),
            season=StatLine.from_dict(d.get("season", {})),
            playoffs=StatLine.from_dict(d.get("playoffs", {})),
            career=list(d.get("career", [])),
        )
