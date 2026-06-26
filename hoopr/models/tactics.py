"""Team tactical settings.

Pure data: the engine (``sim/ratings.py`` and ``sim/engine.py``) reads these and maps them to
numeric modifiers. Each setting is a labelled option so the UI can cycle through choices.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

# Each setting: ordered options; the first is the neutral default.
PACE_OPTIONS: Tuple[str, ...] = ("Balanced", "Slow", "Fast")
OFF_FOCUS_OPTIONS: Tuple[str, ...] = ("Balanced", "Inside", "Perimeter")
BALL_MOVEMENT_OPTIONS: Tuple[str, ...] = ("Balanced", "Motion", "Iso")
DEF_SCHEME_OPTIONS: Tuple[str, ...] = ("Man", "Switch", "Zone")
DEF_PRESSURE_OPTIONS: Tuple[str, ...] = ("Balanced", "Conservative", "Aggressive")
REBOUND_FOCUS_OPTIONS: Tuple[str, ...] = ("Balanced", "Crash Boards", "Get Back")

SETTINGS: Dict[str, Tuple[str, ...]] = {
    "pace": PACE_OPTIONS,
    "off_focus": OFF_FOCUS_OPTIONS,
    "ball_movement": BALL_MOVEMENT_OPTIONS,
    "def_scheme": DEF_SCHEME_OPTIONS,
    "def_pressure": DEF_PRESSURE_OPTIONS,
    "rebound_focus": REBOUND_FOCUS_OPTIONS,
}

SETTING_LABELS: Dict[str, str] = {
    "pace": "Pace",
    "off_focus": "Offensive Focus",
    "ball_movement": "Ball Movement",
    "def_scheme": "Defensive Scheme",
    "def_pressure": "Defensive Pressure",
    "rebound_focus": "Rebounding",
}


@dataclass
class Tactics:
    pace: str = "Balanced"
    off_focus: str = "Balanced"
    ball_movement: str = "Balanced"
    def_scheme: str = "Man"
    def_pressure: str = "Balanced"
    rebound_focus: str = "Balanced"

    def get(self, key: str) -> str:
        return getattr(self, key)

    def cycle(self, key: str) -> None:
        """Advance a setting to its next option (wrapping)."""
        options = SETTINGS[key]
        current = getattr(self, key)
        idx = (options.index(current) + 1) % len(options)
        setattr(self, key, options[idx])

    def items(self) -> List[Tuple[str, str, str]]:
        """Return (key, label, value) triples in display order."""
        return [(k, SETTING_LABELS[k], getattr(self, k)) for k in SETTINGS]

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in SETTINGS}

    @classmethod
    def from_dict(cls, d: dict) -> "Tactics":
        valid = {}
        for k, options in SETTINGS.items():
            v = d.get(k)
            valid[k] = v if v in options else options[0]
        return cls(**valid)
