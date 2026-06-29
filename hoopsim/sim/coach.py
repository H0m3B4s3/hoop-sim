"""Interactive end-of-game coaching.

The :class:`~hoopr.sim.engine.GameSim` is UI-agnostic; when a human wants to take over the
crunch-time decisions of a watched game it is handed a :class:`Coach`. At each of the user team's
possessions inside the closing window the engine builds a read-only :class:`CoachView`, calls
``coach.decide(view)``, and applies the returned :class:`CoachOrders` (timeout, substitution,
tempo, deliberate foul). After the possession resolves it calls ``coach.narrate(...)`` so the UI
can show what happened. The default :class:`Coach` is a no-op (lets the engine play it straight),
so non-interactive sims are unaffected; the console implementation lives in
``hoopr.ui.screens.live_coach`` to keep this module free of UI imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Situational lineup presets the UI offers as one-tap fives. Each maps a player's ratings to a
# fit score; the engine fills the five with the best-fitting available players. Order is display
# order. "closers" mirrors the engine's own clutch pick (best overall).
PRESET_LABELS: Tuple[Tuple[str, str, str], ...] = (
    ("closers", "Closers", "your best five"),
    ("shooters", "Shooters", "need points / a three"),
    ("stoppers", "Stoppers", "get a stop, protect a lead"),
    ("ft", "FT Team", "they're going to foul"),
)

# Per-preset rating weights. Keys are Player.ratings fields; "overall" is the composite. Scores
# are a weighted sum, so the magnitudes only matter relative to each other within a preset.
PRESET_WEIGHTS: Dict[str, Dict[str, float]] = {
    "closers": {"overall": 1.0},
    "shooters": {"three_point": 0.6, "free_throw": 0.25, "off_iq": 0.15},
    "stoppers": {"perimeter_def": 0.4, "interior_def": 0.3, "rebounding": 0.3},
    "ft": {"free_throw": 0.7, "overall": 0.3},
}

# Offensive sets: the look to hunt this possession. Display order; "motion" is the neutral default.
OFFENSIVE_SETS: Tuple[Tuple[str, str], ...] = (
    ("motion", "Run offense"),
    ("iso", "Iso star"),
    ("inside", "Pound inside"),
    ("spread", "Spread / kick"),
)


@dataclass
class PlayerView:
    """A single player's crunch-time status, for display and substitution menus."""
    pid: int
    name: str
    pos: str
    overall: int
    fouls: int
    fatigue: float           # 0 (fresh) .. 100 (gassed)
    secs: float              # seconds played so far
    fouled_out: bool = False


@dataclass
class CoachView:
    """Read-only snapshot handed to the coach at one crunch-time decision point."""
    quarter: int
    periods: int
    clock: float
    period_label: str        # "quarter" | "half"
    home_abbrev: str
    away_abbrev: str
    home_score: int
    away_score: int
    user_is_home: bool
    user_on_offense: bool
    user_timeouts: int
    opp_timeouts: int
    user_in_bonus: bool
    opp_in_bonus: bool
    on_court: List[PlayerView] = field(default_factory=list)   # user team, five players
    bench: List[PlayerView] = field(default_factory=list)      # available user subs
    first_engagement: bool = False
    # True for a mid-possession free-throw sub window: the only legal action is a substitution
    # (no tempo/foul/timeout) before the final FT, so the new five contests the live rebound.
    sub_only: bool = False
    # One-tap situational fives the UI can load into the working lineup. Maps a preset key
    # (see PRESET_LABELS) to the five pids that best fit it among the currently available players.
    presets: Dict[str, List[int]] = field(default_factory=dict)
    # A short, non-binding read of the situation from the bench ("they have no timeouts...").
    hint: str = ""

    @property
    def user_score(self) -> int:
        return self.home_score if self.user_is_home else self.away_score

    @property
    def opp_score(self) -> int:
        return self.away_score if self.user_is_home else self.home_score

    @property
    def user_lead(self) -> int:
        return self.user_score - self.opp_score


@dataclass
class CoachOrders:
    """What the coach wants to do this possession. The engine applies all that are relevant."""
    timeout: bool = False
    # Offense only: "normal" plays it out, "bleed" chews the shot clock while leading,
    # "hold" milks it for the final shot of the game, "quick3" gets a fast three up while trailing.
    tempo: str = "normal"
    # Defense only: "auto" defers to the team's tactics, "foul" sends them to the line now,
    # "no" tells them not to foul this trip.
    defensive_foul: str = "auto"
    # Offense only: the kind of look to hunt this trip (orthogonal to tempo). "motion" runs the
    # offense straight, "iso" funnels the ball to the top scorer, "inside" pounds the rim and
    # draws fouls, "spread" hunts a three. The engine biases shooter/shot selection accordingly.
    offensive_set: str = "motion"
    # New on-court five for the user team (pids); None leaves the lineup unchanged.
    lineup: Optional[List[int]] = None


class Coach:
    """Default no-op coach: the engine plays crunch time on its own."""

    def decide(self, view: CoachView) -> CoachOrders:
        return CoachOrders()

    def narrate(self, lines: List[str]) -> None:
        """Called after a coached possession resolves, with the new play-by-play lines."""
        return None
