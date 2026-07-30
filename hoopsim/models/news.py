"""League news items — the wire that makes everything else in the sim visible.

The engine already computes a great deal that a reader would care about and then throws it away:
a 50-point night, a torn ACL, a coach fired after a 22-win season, a trade, a player crossing
20,000 career points. Each of those was a number that moved inside a system and never surfaced.
A :class:`NewsItem` is that moment, captured at the point it happens.

Items are **self-contained snapshots**, like the résumés in ``systems/legacy.py``: the headline
text is frozen at write time rather than re-rendered later from live objects. A trade headline
must still read correctly after the players in it have been traded again, retired, or dropped
from the league entirely.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Categories, used for filtering in the UI. Keep these stable — they are persisted in saves.
CATEGORIES = ("game", "injury", "transaction", "award", "milestone", "draft", "coaching")

CATEGORY_LABELS = {
    "game": "On the Court",
    "injury": "Injuries",
    "transaction": "Transactions",
    "award": "Awards",
    "milestone": "Milestones",
    "draft": "Draft",
    "coaching": "Coaching",
}

# Importance tiers. The feed defaults to showing everything, but a "big stories only" filter and
# any future digest both need a way to rank, and sorting by recency alone buries the ACL tear
# under a hundred box-score lines.
MINOR, NORMAL, MAJOR = 1, 2, 3


@dataclass
class NewsItem:
    year: int
    day: int
    category: str
    headline: str
    importance: int = NORMAL
    tids: List[int] = field(default_factory=list)     # teams the item concerns
    pids: List[int] = field(default_factory=list)     # players the item concerns
    detail: str = ""                                  # optional second line

    def to_dict(self) -> dict:
        return {"year": self.year, "day": self.day, "category": self.category,
                "headline": self.headline, "importance": self.importance,
                "tids": list(self.tids), "pids": list(self.pids), "detail": self.detail}

    @classmethod
    def from_dict(cls, d: dict) -> "NewsItem":
        cat = d.get("category", "game")
        return cls(
            year=d.get("year", 0),
            day=d.get("day", 0),
            category=cat if cat in CATEGORIES else "game",
            headline=d.get("headline", ""),
            importance=int(d.get("importance", NORMAL)),
            tids=list(d.get("tids", [])),
            pids=list(d.get("pids", [])),
            detail=d.get("detail", ""),
        )
