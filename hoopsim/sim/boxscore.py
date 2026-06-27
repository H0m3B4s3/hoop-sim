"""Game result containers: per-player box scores and a play-by-play log."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from hoopsim.models.stats import StatLine


@dataclass
class PBPEvent:
    quarter: int
    seconds_left: int
    home_score: int
    away_score: int
    tid: Optional[int]
    text: str

    @property
    def clock(self) -> str:
        m, s = divmod(max(0, self.seconds_left), 60)
        return f"{m}:{s:02d}"


@dataclass
class GameResult:
    home_tid: int
    away_tid: int
    home_score: int = 0
    away_score: int = 0
    box: Dict[int, StatLine] = field(default_factory=dict)        # pid -> line
    home_starters: List[int] = field(default_factory=list)
    away_starters: List[int] = field(default_factory=list)
    line_score: List[Tuple[int, int]] = field(default_factory=list)  # (home, away) per period
    period_label: str = "quarter"                                  # "quarter" | "half"
    overtimes: int = 0
    pbp: List[PBPEvent] = field(default_factory=list)
    # In-game injuries to apply at the season layer: (pid, games, description, severity).
    injuries: List[Tuple[int, int, str, str]] = field(default_factory=list)

    @property
    def winner(self) -> int:
        return self.home_tid if self.home_score > self.away_score else self.away_tid

    @property
    def loser(self) -> int:
        return self.away_tid if self.home_score > self.away_score else self.home_tid

    def line(self, pid: int) -> StatLine:
        if pid not in self.box:
            self.box[pid] = StatLine()
        return self.box[pid]

    def team_line(self, pids: List[int]) -> StatLine:
        total = StatLine()
        for pid in pids:
            if pid in self.box:
                total.add(self.box[pid])
        return total
