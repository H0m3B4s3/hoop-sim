"""Front-office difficulty: how hard the league bargains with the user.

Only deals with the user's team are affected. AI-to-AI trades and AI signings always run at
normal, so changing difficulty never reshapes how the rest of the league builds its rosters.
"""
from __future__ import annotations

from hoopsim.config import DEFAULT_DIFFICULTY, DIFFICULTY_LEVELS, VETERAN_MINIMUM
from hoopsim.models.world import World

LABELS = {"easy": "Easy", "normal": "Normal", "hard": "Hard"}


def level(world: World) -> str:
    return world.difficulty if world.difficulty in DIFFICULTY_LEVELS else DEFAULT_DIFFICULTY


def trade_margin_bonus(world: World) -> float:
    return DIFFICULTY_LEVELS[level(world)]["trade_margin"]


def user_price(world: World, salary: int) -> int:
    """What a player asks the user for, given the base price an AI team would pay."""
    factor = DIFFICULTY_LEVELS[level(world)]["price"]
    if factor == 1.0:
        return salary
    return max(VETERAN_MINIMUM, int(round(salary * factor / 100_000) * 100_000))
