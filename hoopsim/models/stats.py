"""Counting-stat containers shared by the engine, players, and teams.

A :class:`StatLine` accumulates raw box-score counters. The same structure serves a single
game's box score, a player's season totals, and a team's season totals. Derived rates
(per-game, shooting percentages) are computed on demand.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Dict

_COUNTERS = (
    "gp", "gs", "secs",
    "pts", "fgm", "fga", "tpm", "tpa", "ftm", "fta",
    "oreb", "dreb", "ast", "stl", "blk", "tov", "pf",
    "plus_minus",
)


@dataclass
class StatLine:
    gp: int = 0          # games played
    gs: int = 0          # games started
    secs: int = 0        # seconds played
    pts: int = 0
    fgm: int = 0
    fga: int = 0
    tpm: int = 0         # three-point makes
    tpa: int = 0
    ftm: int = 0
    fta: int = 0
    oreb: int = 0
    dreb: int = 0
    ast: int = 0
    stl: int = 0
    blk: int = 0
    tov: int = 0
    pf: int = 0          # personal fouls
    plus_minus: int = 0

    # -- derived ------------------------------------------------------------
    @property
    def reb(self) -> int:
        return self.oreb + self.dreb

    @property
    def minutes(self) -> float:
        return self.secs / 60.0

    @property
    def fg_pct(self) -> float:
        return self.fgm / self.fga if self.fga else 0.0

    @property
    def tp_pct(self) -> float:
        return self.tpm / self.tpa if self.tpa else 0.0

    @property
    def ft_pct(self) -> float:
        return self.ftm / self.fta if self.fta else 0.0

    @property
    def ts_pct(self) -> float:
        """True shooting percentage."""
        denom = 2 * (self.fga + 0.44 * self.fta)
        return self.pts / denom if denom else 0.0

    def per_game(self, counter: str) -> float:
        if self.gp == 0:
            return 0.0
        return getattr(self, counter) / self.gp

    @property
    def ppg(self) -> float:
        return self.per_game("pts")

    @property
    def rpg(self) -> float:
        return self.reb / self.gp if self.gp else 0.0

    @property
    def apg(self) -> float:
        return self.per_game("ast")

    @property
    def mpg(self) -> float:
        return self.minutes / self.gp if self.gp else 0.0

    # -- mutation -----------------------------------------------------------
    def add(self, other: "StatLine") -> None:
        for name in _COUNTERS:
            setattr(self, name, getattr(self, name) + getattr(other, name))

    def reset(self) -> None:
        for name in _COUNTERS:
            setattr(self, name, 0)

    # -- serialization ------------------------------------------------------
    def to_dict(self) -> Dict[str, int]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, d: Dict[str, int]) -> "StatLine":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})
