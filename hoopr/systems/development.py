"""Offseason player development and aging.

Young players climb toward their potential (faster with minutes and work ethic); players in
their prime plateau; veterans decline — losing athleticism first while keeping their IQ. This
runs once per offseason for every player in the league.
"""
from __future__ import annotations

from hoopr.models.attributes import clamp_rating
from hoopr.models.player import Player
from hoopr.models.world import World
from hoopr.gen.playergen import SKILL_RATINGS

_PHYSICAL = {"athleticism", "speed", "vertical", "strength", "stamina"}
_IQ = {"off_iq", "def_iq", "basketball_iq"}


def _overall_delta(player: Player, rng) -> float:
    gap = player.potential - player.overall
    age = player.age
    if age <= 23:
        growth = gap * rng.uniform(0.18, 0.38) + rng.gauss(0.5, 1.0)
    elif age <= 26:
        growth = gap * rng.uniform(0.10, 0.22) + rng.gauss(0.2, 1.0)
    elif age <= 29:
        growth = rng.gauss(0.0, 1.2)
    elif age <= 32:
        growth = rng.gauss(-1.6, 1.2)
    elif age <= 35:
        growth = rng.gauss(-3.2, 1.5)
    else:
        growth = rng.gauss(-5.0, 2.0)

    if age <= 26 and growth > 0:
        mpg = player.season.mpg if player.season.gp else 0.0
        growth *= 0.6 + min(1.0, mpg / 28.0) * 0.8        # playing time accelerates growth
    growth += (player.ratings["work_ethic"] - 70) * 0.02
    return growth


def _apply_delta(player: Player, delta: float, rng) -> None:
    for skill in SKILL_RATINGS:
        if delta < 0:
            if skill in _IQ:
                change = rng.gauss(0.3, 0.6)              # vets keep getting smarter
            elif skill in _PHYSICAL:
                change = delta * 1.6 + rng.gauss(0, 1.2)  # athleticism fades first
            else:
                change = delta * 0.9 + rng.gauss(0, 1.2)
        else:
            change = delta + rng.gauss(0, 1.0)
        player.ratings[skill] = clamp_rating(player.ratings[skill] + change)


def develop_player(player: Player, rng) -> int:
    """Develop one player; return the change in overall (for reporting)."""
    before = player.overall
    delta = _overall_delta(player, rng)
    _apply_delta(player, delta, rng)
    # Potential converges toward overall as a player ages out of his growth window.
    if player.age > 27 and player.potential > player.overall:
        player.potential = max(player.overall, player.potential - rng.randint(0, 2))
    player.potential = max(player.potential, player.overall)
    return player.overall - before


def develop_all(world: World) -> None:
    for player in world.players.values():
        develop_player(player, world.rng)
