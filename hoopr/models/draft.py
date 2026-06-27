"""Draft structures.

A :class:`DraftClass` is a pool of generated prospect players plus the pick order. Prospects
are ordinary :class:`~hoopr.models.player.Player` objects with no team; once picked they sign a
rookie-scale deal and join the drafting team's roster.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class DraftPick:
    """A tradeable future draft selection.

    A pick's *slot* in a given draft is determined by ``original_tid``'s standing that year;
    ``owner_tid`` is whoever currently controls it (changes when the pick is traded). At most
    one pick exists per ``(year, round, original_tid)`` key.
    """
    year: int
    round: int            # 1 or 2
    original_tid: int     # whose draft slot this is (sets the pick position)
    owner_tid: int        # who currently controls it

    @property
    def key(self) -> Tuple[int, int, int]:
        return (self.year, self.round, self.original_tid)

    def to_dict(self) -> dict:
        return {"year": self.year, "round": self.round,
                "original_tid": self.original_tid, "owner_tid": self.owner_tid}

    @classmethod
    def from_dict(cls, d: dict) -> "DraftPick":
        return cls(year=d["year"], round=d["round"],
                   original_tid=d["original_tid"], owner_tid=d["owner_tid"])


@dataclass
class DraftClass:
    year: int
    prospect_ids: List[int] = field(default_factory=list)   # generated, undrafted players
    order: List[int] = field(default_factory=list)          # owner team ids, pick 1..N (two rounds)
    origins: List[int] = field(default_factory=list)        # original team per slot (for "via" labels)
    picks_made: Dict[int, int] = field(default_factory=dict)  # pick_number (1-based) -> pid
    current_pick: int = 1                                    # next pick to make (1-based)

    @property
    def total_picks(self) -> int:
        return len(self.order)

    @property
    def complete(self) -> bool:
        return self.current_pick > self.total_picks

    def team_on_clock(self) -> int:
        return self.order[self.current_pick - 1]

    def remaining_prospects(self) -> List[int]:
        drafted = set(self.picks_made.values())
        return [pid for pid in self.prospect_ids if pid not in drafted]

    def record_pick(self, pid: int) -> None:
        self.picks_made[self.current_pick] = pid
        self.current_pick += 1

    def origin_for(self, pick_no: int) -> int:
        """Original team whose slot ``pick_no`` (1-based) is, defaulting to the owner."""
        idx = pick_no - 1
        if 0 <= idx < len(self.origins):
            return self.origins[idx]
        return self.order[idx]

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "prospect_ids": list(self.prospect_ids),
            "order": list(self.order),
            "origins": list(self.origins),
            "picks_made": {str(k): v for k, v in self.picks_made.items()},
            "current_pick": self.current_pick,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DraftClass":
        return cls(
            year=d["year"],
            prospect_ids=list(d.get("prospect_ids", [])),
            order=list(d.get("order", [])),
            origins=list(d.get("origins", [])),
            picks_made={int(k): v for k, v in d.get("picks_made", {}).items()},
            current_pick=d.get("current_pick", 1),
        )
