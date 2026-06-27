"""League-level structures: phases, scheduled games, and standings logic."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from hoopsim.models.team import Team


class Phase:
    """Ordered phases of a season. Stored as plain strings for JSON friendliness."""

    PRESEASON = "preseason"
    REGULAR_SEASON = "regular_season"
    PLAY_IN = "play_in"
    PLAYOFFS = "playoffs"
    DRAFT = "draft"
    FREE_AGENCY = "free_agency"
    OFFSEASON = "offseason"

    ORDER: List[str] = [
        PRESEASON, REGULAR_SEASON, PLAY_IN, PLAYOFFS, DRAFT, FREE_AGENCY, OFFSEASON,
    ]

    LABELS = {
        PRESEASON: "Preseason",
        REGULAR_SEASON: "Regular Season",
        PLAY_IN: "Play-In Tournament",
        PLAYOFFS: "Playoffs",
        DRAFT: "Draft",
        FREE_AGENCY: "Free Agency",
        OFFSEASON: "Offseason",
    }

    @classmethod
    def label(cls, phase: str) -> str:
        return cls.LABELS.get(phase, phase.title())


@dataclass
class Game:
    gid: int
    day: int                       # integer game-day index within the season
    home: int                      # home team id
    away: int                      # away team id
    home_score: int = 0
    away_score: int = 0
    played: bool = False
    is_playoff: bool = False
    series_id: Optional[str] = None

    @property
    def winner(self) -> Optional[int]:
        if not self.played:
            return None
        return self.home if self.home_score > self.away_score else self.away

    @property
    def loser(self) -> Optional[int]:
        if not self.played:
            return None
        return self.away if self.home_score > self.away_score else self.home

    def involves(self, tid: int) -> bool:
        return self.home == tid or self.away == tid

    def opponent_of(self, tid: int) -> int:
        return self.away if self.home == tid else self.home

    def to_dict(self) -> dict:
        return {
            "gid": self.gid, "day": self.day, "home": self.home, "away": self.away,
            "home_score": self.home_score, "away_score": self.away_score,
            "played": self.played, "is_playoff": self.is_playoff, "series_id": self.series_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Game":
        return cls(
            gid=d["gid"], day=d["day"], home=d["home"], away=d["away"],
            home_score=d.get("home_score", 0), away_score=d.get("away_score", 0),
            played=d.get("played", False), is_playoff=d.get("is_playoff", False),
            series_id=d.get("series_id"),
        )


def _sort_key(team: Team):
    conf_gp = team.conf_wins + team.conf_losses
    conf_pct = team.conf_wins / conf_gp if conf_gp else 0.0
    # Higher is better -> negate for ascending sort; tid as a stable final tiebreaker.
    return (-team.win_pct, -conf_pct, -team.point_diff, team.tid)


def standings(teams: List[Team]) -> List[Team]:
    """Order teams by win pct, then conference record, then point differential."""
    return sorted(teams, key=_sort_key)


def conference_standings(teams: List[Team], conference: str) -> List[Team]:
    return standings([t for t in teams if t.conference == conference])
