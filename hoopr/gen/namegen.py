"""Procedural name generation from pooled name lists."""
from __future__ import annotations

import json
import os
from typing import List, Set, Tuple

from hoopr.rng import Rng

_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "names.json")

_first: List[str] = []
_last: List[str] = []


def _load() -> None:
    global _first, _last
    if _first and _last:
        return
    with open(_DATA_PATH, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    _first = data["first"]
    _last = data["last"]


class NameGenerator:
    """Generates names, avoiding exact duplicates within a run when possible."""

    def __init__(self, rng: Rng) -> None:
        _load()
        self.rng = rng
        self._used: Set[Tuple[str, str]] = set()

    def name(self) -> Tuple[str, str]:
        for _ in range(12):
            first = self.rng.choice(_first)
            last = self.rng.choice(_last)
            if (first, last) not in self._used:
                self._used.add((first, last))
                return first, last
        # Fall back to a suffixed surname if the pool is exhausted.
        first = self.rng.choice(_first)
        last = self.rng.choice(_last) + " Jr."
        self._used.add((first, last))
        return first, last
