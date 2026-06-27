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

# Coach-mode end-game instructions (the engine applies these in crunch time).
CRUNCH_FOUL_OPTIONS: Tuple[str, ...] = ("Auto", "Aggressive", "Never")
FOUL_UP_3_OPTIONS: Tuple[str, ...] = ("No", "Yes")
CRUNCH_LINEUP_OPTIONS: Tuple[str, ...] = ("Closers", "Rotation")

SETTINGS: Dict[str, Tuple[str, ...]] = {
    "pace": PACE_OPTIONS,
    "off_focus": OFF_FOCUS_OPTIONS,
    "ball_movement": BALL_MOVEMENT_OPTIONS,
    "def_scheme": DEF_SCHEME_OPTIONS,
    "def_pressure": DEF_PRESSURE_OPTIONS,
    "rebound_focus": REBOUND_FOCUS_OPTIONS,
    "crunch_foul": CRUNCH_FOUL_OPTIONS,
    "foul_up_3": FOUL_UP_3_OPTIONS,
    "crunch_lineup": CRUNCH_LINEUP_OPTIONS,
}

SETTING_LABELS: Dict[str, str] = {
    "pace": "Pace",
    "off_focus": "Offensive Focus",
    "ball_movement": "Ball Movement",
    "def_scheme": "Defensive Scheme",
    "def_pressure": "Defensive Pressure",
    "rebound_focus": "Rebounding",
    "crunch_foul": "Foul When Trailing (late)",
    "foul_up_3": "Foul Up 3 (last seconds)",
    "crunch_lineup": "Crunch-Time Lineup",
}


@dataclass
class Tactics:
    pace: str = "Balanced"
    off_focus: str = "Balanced"
    ball_movement: str = "Balanced"
    def_scheme: str = "Man"
    def_pressure: str = "Balanced"
    rebound_focus: str = "Balanced"
    crunch_foul: str = "Auto"
    foul_up_3: str = "No"
    crunch_lineup: str = "Closers"

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
