"""Season momentum: how a player's morale moves game to game, and the team's form read.

Morale is the *form* input to the realization model (see :mod:`hoopsim.sim.ratings`): confidence a
player carries across games, capped so it only ever lets him reach his ceiling — never exceed it.
It is driven mostly by **winning** (a winning locker room plays loose, a losing one tightens up),
modulated by a player's **own game** versus what a player of his caliber should produce, and by his
**role** (a healthy player buried on the bench sours). Every game it also mean-reverts toward a
personal baseline, so streaks and slumps fade instead of running away.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from hoopsim.models.stats import StatLine

if TYPE_CHECKING:                                  # avoid import cycles at runtime
    from hoopsim.models.world import World
    from hoopsim.sim.boxscore import GameResult

# -- tunables ----------------------------------------------------------------
MORALE_BASELINE = 70           # neutral form (= full realization, today's tuning)
MEAN_REVERT = 0.12             # fraction of the gap to baseline closed each game
W_RESULT = 2.4                 # winning is the dominant driver of confidence
W_PERF = 1.3                   # individual game vs. expectation for a player of his caliber
W_ROLE = 1.0                   # role satisfaction (minutes); a healthy DNP sours
MAX_GAME_DELTA = 6.0           # cap on a single game's swing before reversion
MORALE_MIN, MORALE_MAX = 20, 99
ROTATION_MIN = 14.0            # minutes at/above which a player feels like a rotation piece
GARBAGE_MIN = 6.0              # minutes below which it was a DNP / mop-up appearance

# Offseason carryover. Chemistry rusts a little over the summer but a core that logged heavy
# minutes together is far above the gelled threshold, so it returns intact; only lightly-used or
# brand-new pairings start cold. Morale reverts most of the way to baseline — a fresh season brings
# optimism, though last year's slump or swagger lingers a touch.
CHEM_CARRY_CAP = 60_000.0      # cap banked pair-time so it stays bounded and decay can bite
CHEM_RETENTION = 0.70          # fraction of (capped) shared time retained into the next season
MORALE_OFFSEASON_REVERT = 0.6  # fraction of the gap to baseline closed over the offseason

def game_score(s: StatLine) -> float:
    """Hollinger game score: one number for how good a single-game line was."""
    return (s.pts + 0.4 * s.fgm - 0.7 * s.fga - 0.4 * (s.fta - s.ftm)
            + 0.7 * s.oreb + 0.3 * s.dreb + s.stl + 0.7 * s.ast + 0.7 * s.blk
            - 0.4 * s.pf - s.tov)


def _result_signal(won: bool, margin: int) -> float:
    """+1 for a win, −1 for a loss, nudged up to ±0.5 more by the margin."""
    sign = 1.0 if won else -1.0
    return sign * (1.0 + min(0.5, margin / 30.0))


def _expected_game_score(overall: int, minutes: float) -> float:
    """A rough bar for a player's production this game given his caliber and floor time."""
    return max(0.0, (overall - 62) * minutes * 0.013)


def _personal_baseline(work_ethic: int) -> float:
    """High-character players settle a touch higher and steadier; low ones a touch lower."""
    return MORALE_BASELINE + (work_ethic - 70) * 0.15


def _new_morale(morale: int, delta: float, baseline: float) -> int:
    morale = morale + max(-MAX_GAME_DELTA, min(MAX_GAME_DELTA, delta))
    morale += (baseline - morale) * MEAN_REVERT          # mean-revert toward the personal baseline
    return int(round(max(MORALE_MIN, min(MORALE_MAX, morale))))


def update_morale(world: "World", home, away, result: "GameResult") -> None:
    """Update every rostered player's morale from one finished game.

    Healthy players feel the result, their own game, and their role; injured players (who couldn't
    affect it) simply drift toward their baseline.
    """
    home_won = result.home_score > result.away_score
    margin = abs(result.home_score - result.away_score)
    for team, won in ((home, home_won), (away, not home_won)):
        for pid in team.roster:
            p = world.players.get(pid)
            if p is None:
                continue
            baseline = _personal_baseline(p.ratings.get("work_ethic", 70))
            if p.is_injured:                              # not his game to influence
                p.morale = _new_morale(p.morale, 0.0, baseline)
                continue
            line = result.box.get(pid)
            minutes = (line.secs / 60.0) if line else 0.0

            delta = W_RESULT * _result_signal(won, margin)
            if minutes < GARBAGE_MIN:                     # healthy but barely (or never) played
                delta += W_ROLE * -0.6
            elif minutes < ROTATION_MIN:
                delta += W_ROLE * -0.15
            if line is not None and minutes >= GARBAGE_MIN:
                exp = _expected_game_score(p.overall, minutes)
                perf = max(-1.0, min(1.0, (game_score(line) - exp) / 6.0))
                delta += W_PERF * perf
            p.morale = _new_morale(p.morale, delta, baseline)


def offseason_reset(world: "World") -> None:
    """Carry chemistry and morale across the offseason (called between seasons, never before #1).

    Chemistry decays toward cold for thin pairings while established cores (banked well past the
    gelled threshold) survive; morale drifts most of the way back to each player's baseline.
    """
    for team in world.teams.values():
        team.chemistry = {k: min(CHEM_CARRY_CAP, v) * CHEM_RETENTION
                          for k, v in team.chemistry.items()}
    for p in world.players.values():
        baseline = _personal_baseline(p.ratings.get("work_ethic", 70))
        p.morale = int(round(p.morale + (baseline - p.morale) * MORALE_OFFSEASON_REVERT))
