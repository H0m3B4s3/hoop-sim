"""Salary-cap math: payroll, cap space, luxury tax, max/market salaries, and asset value.

A faithful-in-spirit simplification of the NBA cap: teams may exceed the cap (the cap is "soft"),
pay a luxury tax above the tax line, match salary in trades, and always sign minimum deals.
"""
from __future__ import annotations

from typing import Tuple

from hoopr.config import (LUXURY_TAX_LINE, LUXURY_TAX_RATE, MAX_SALARY_TIERS, MID_LEVEL_EXCEPTION,
                          ROSTER_MAX, SALARY_CAP, TRADE_MATCH_BUFFER, TRADE_MATCH_FACTOR,
                          VETERAN_MINIMUM)
from hoopr.models.player import Player
from hoopr.models.team import Team, team_salary
from hoopr.models.world import World


def payroll(world: World, team: Team) -> int:
    return team_salary(team, world.players)


def cap_space(world: World, team: Team) -> int:
    return max(0, SALARY_CAP - payroll(world, team))


def over_cap(world: World, team: Team) -> bool:
    return payroll(world, team) > SALARY_CAP


def luxury_tax(world: World, team: Team) -> int:
    over = payroll(world, team) - LUXURY_TAX_LINE
    return int(over * LUXURY_TAX_RATE) if over > 0 else 0


def max_salary(experience: int) -> int:
    fraction = MAX_SALARY_TIERS[0][1]
    for min_years, frac in MAX_SALARY_TIERS:
        if experience >= min_years:
            fraction = frac
    return int(SALARY_CAP * fraction)


def base_salary_for(ovr: int) -> int:
    """Deterministic 'fair' annual salary for a given overall (no noise)."""
    if ovr >= 85:
        base = 25_000_000 + (ovr - 85) * 2_200_000
    elif ovr >= 80:
        base = 16_000_000 + (ovr - 80) * 1_800_000
    elif ovr >= 76:
        base = 9_000_000 + (ovr - 76) * 1_600_000
    elif ovr >= 72:
        base = 4_500_000 + (ovr - 72) * 1_000_000
    elif ovr >= 68:
        base = 2_500_000 + (ovr - 68) * 500_000
    else:
        base = VETERAN_MINIMUM
    return base


def market_salary(player: Player) -> int:
    """Estimated annual salary a free agent would command."""
    base = base_salary_for(player.overall)
    if player.age <= 24 and player.scouted_potential() > player.overall + 4:
        base *= 1.10
    if player.age >= 33:
        base *= 0.72
    base = min(base, max_salary(player.experience))
    return max(VETERAN_MINIMUM, int(round(base / 100_000) * 100_000))


def trade_value(player: Player) -> float:
    """Unitless asset value blending production, age/upside, and contract surplus."""
    ovr = player.overall
    base = max(0.0, (ovr - 45)) ** 1.6 / 8.0
    age = player.age
    if age <= 23:
        af = 1.18
    elif age <= 26:
        af = 1.08
    elif age <= 29:
        af = 1.0
    elif age <= 32:
        af = 0.85
    else:
        af = 0.65
    pot_bonus = max(0, player.scouted_potential() - ovr) * (0.30 if age <= 25 else 0.10)
    value = base * af + pot_bonus
    surplus = (market_salary(player) - player.contract.current_salary) / 5_000_000.0
    return max(0.1, value + surplus)


# ---------------------------------------------------------------------------
# Trade & signing legality
# ---------------------------------------------------------------------------
def trade_matching_ok(space_before: int, outgoing: int, incoming: int) -> bool:
    """Can a team legally take back ``incoming`` salary given what it sends out?"""
    allowance = max(space_before + outgoing,
                    int(outgoing * TRADE_MATCH_FACTOR) + TRADE_MATCH_BUFFER)
    return incoming <= allowance


def can_sign(world: World, team: Team, salary: int) -> Tuple[bool, str]:
    """Whether a team may sign a free agent at ``salary`` (minimum always allowed)."""
    if len(team.roster) >= ROSTER_MAX:
        return False, "Roster is full."
    if salary <= VETERAN_MINIMUM:
        return True, "Minimum contract."
    space = cap_space(world, team)
    if salary <= space:
        return True, "Uses cap space."
    if salary <= MID_LEVEL_EXCEPTION:
        return True, "Mid-level exception."
    return False, "Not enough cap space."
