"""Procedural name generation from pooled name lists.

Names are drawn from the world's shared :class:`~hoopr.rng.Rng`, and the dedup retry loop in
``NameGenerator.name`` consumes a *variable* number of draws (more collisions in a small pool ->
more draws). So the contents of ``data/names.json`` are part of the reproducibility surface:
a fixed pool + fixed seed reproduces a league exactly, but editing the pool shifts the shared
stream and changes everything generated afterward (ratings, ages, AI outcomes) -- not just the
names. This is accepted: settle on a names.json before treating seeds as shareable, and expect
golden-seed tests to need re-baselining whenever the pool changes.
"""
from __future__ import annotations

import json
import os
from typing import List, Set, Tuple

from hoopr.rng import Rng

_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "names.json")

_first: List[str] = []
_last: List[str] = []

# Rare generational suffixes, ordered by real-world frequency: Jr. most common, then III, then
# II; IV is uncommon and V is a genuine rarity. ~7% of players carry any suffix at all.
_SUFFIXES = ("Jr.", "III", "II", "IV", "V")
_SUFFIX_WEIGHTS = (58, 24, 16, 1.7, 0.3)
_SUFFIX_CHANCE = 0.07


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
        # FUTURE (immersion, not needed for dev): names are picked uniformly, so a distinctive
        # surname is as common as a generic one. Weight by popularity (e.g. tiered common/flavor
        # pools sampled at different rates) so "Jones" appears often and "Jokic" rarely.
        for _ in range(12):
            first = self.rng.choice(_first)
            last = self.rng.choice(_last)
            if (first, last) not in self._used:        # dedup on the base (suffix-free) pair
                self._used.add((first, last))
                return first, self._suffixed(last)
        # Fall back to a suffixed surname if the pool is exhausted.
        first = self.rng.choice(_first)
        last = self.rng.choice(_last) + " Jr."
        self._used.add((first, last))
        return first, last

    def _suffixed(self, last: str) -> str:
        """Occasionally tack on a rare generational suffix (Jr./II/III/IV/V)."""
        if self.rng.chance(_SUFFIX_CHANCE):
            return f"{last} {self.rng.weighted_one(_SUFFIXES, _SUFFIX_WEIGHTS)}"
        return last
