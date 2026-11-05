"""Salary-cap math: payroll, cap space, luxury tax, max/market salaries, and asset value.

A faithful-in-spirit simplification of the NBA cap: teams may exceed the cap (the cap is "soft"),
pay a luxury tax above the tax line, match salary in trades, and always sign minimum deals.
"""
from __future__ import annotations

from typing import Tuple

from hoopsim.config import (LUXURY_TAX_RATE, MAX_CONTRACT_YEARS, MAX_SALARY_TIERS,
                          MID_LEVEL_EXCEPTION, ROSTER_MAX, SALARY_CAP, TRADE_MATCH_BUFFER,
                          TRADE_MATCH_FACTOR, VETERAN_MINIMUM)
from hoopsim.models.player import Player
from hoopsim.models.team import Team, team_salary
from hoopsim.models.world import World


def payroll(world: World, team: Team) -> int:
    return team_salary(team, world.players)


def cap_space(world: World, team: Team) -> int:
    return max(0, world.salary_cap - payroll(world, team))


def over_cap(world: World, team: Team) -> bool:
    return payroll(world, team) > world.salary_cap


def luxury_tax(world: World, team: Team) -> int:
    over = payroll(world, team) - world.luxury_tax_line
    return int(over * LUXURY_TAX_RATE) if over > 0 else 0


def max_salary(experience: int, cap: int = SALARY_CAP) -> int:
    fraction = MAX_SALARY_TIERS[0][1]
    for min_years, frac in MAX_SALARY_TIERS:
        if experience >= min_years:
            fraction = frac
    return int(cap * fraction)


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


# A star outweighs any pile of role players, so value climbs steeply past a starter's rating.
# Below STAR_PREMIUM_FROM the curve is flat enough that players stay comparable to draft picks.
STAR_PREMIUM_FROM = 75.0
STAR_PREMIUM_SCALE = 10.0
# How much of the gap to his ceiling a young player's price already includes, by age.
UPSIDE_PRICED_IN = ((21, 0.60), (23, 0.45), (25, 0.25))
# Contract surplus counts per year it runs, so a long bad deal is a real liability.
CONTRACT_YEARS_PRICED = 3


def _projected_rating(player: Player) -> float:
    """The rating a buyer is really paying for: where a young player is headed, not just is."""
    upside = max(0, player.scouted_potential() - player.overall)
    for max_age, share in UPSIDE_PRICED_IN:
        if player.age <= max_age:
            return player.overall + upside * share
    return float(player.overall)


def trade_value(player: Player) -> float:
    """Unitless asset value blending production, age/upside, and contract surplus.

    Can be negative: an overpaid player on a long deal costs a team something to move.
    """
    rating = _projected_rating(player)
    base = max(0.0, rating - 45) ** 1.6 / 8.0
    base *= 1 + (max(0.0, rating - STAR_PREMIUM_FROM) / STAR_PREMIUM_SCALE) ** 2
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
    years = min(CONTRACT_YEARS_PRICED, max(1, player.contract.years_remaining))
    surplus = (market_salary(player) - player.contract.current_salary) / 5_000_000.0 * years
    return base * af + surplus


def pick_value(world: World, pick) -> float:
    """Asset value of a future draft pick, on the same unitless scale as ``trade_value``.

    Driven by the original team's expected finish (a bad team's first-rounder lands a star),
    the round, and a discount for picks further out. In-season we use the live record; before
    games are played we fall back to prestige as a strength proxy.
    """
    team = world.find_team(pick.original_tid)
    if team is not None and team.games_played:
        strength = team.win_pct                      # 0 (worst) .. 1 (best)
    elif team is not None:
        strength = (team.prestige - 1) / 4.0         # prestige 1..5 -> 0..1
    else:
        strength = 0.5
    if pick.round == 1:
        value = 5.0 + (1.0 - strength) * 17.0        # ~5 (late) .. ~22 (top of a bad team)
    else:
        value = 0.5 + (1.0 - strength) * 2.5         # ~0.5 .. ~3.0
    years_out = max(0, pick.year - world.season_year)
    value *= 0.85 ** years_out                       # the future is uncertain
    return round(value, 1)


# ---------------------------------------------------------------------------
# Trade & signing legality
# ---------------------------------------------------------------------------
def trade_matching_ok(space_before: int, outgoing: int, incoming: int) -> bool:
    """Can a team legally take back ``incoming`` salary given what it sends out?"""
    allowance = max(space_before + outgoing,
                    int(outgoing * TRADE_MATCH_FACTOR) + TRADE_MATCH_BUFFER)
    return incoming <= allowance


def can_extend(world: World, team: Team, pid: int) -> Tuple[bool, str]:
    player = world.players.get(pid)
    if player is None or pid not in team.roster:
        return False, "Player is not on your roster."
    if player.contract.years_remaining >= MAX_CONTRACT_YEARS:
        return False, "Contract is already at the maximum length."
    return True, "Eligible to extend."


def extension_offer(world: World, player, *, for_user: bool = False) -> Tuple[int, int]:
    """A reasonable (salary, added years) the team would offer to extend a player. The user's ask
    is scaled by difficulty; AI re-signings always pay the plain market rate."""
    from hoopsim.systems import contract_mood, difficulty
    market = market_salary(player)
    if for_user:
        mood = contract_mood.assess(world, player)
        market = int(round(market * (mood["ask_factor"] or 1.0) / 100_000) * 100_000)
        market = difficulty.user_price(world, market)
    salary = min(market, max_salary(player.experience, world.salary_cap))
    add_years = max(1, min(MAX_CONTRACT_YEARS - player.contract.years_remaining, 4))
    return salary, add_years


def extend_contract(world: World, team: Team, pid: int, salary: int, add_years: int, *,
                    for_user: bool = False) -> Tuple[bool, str]:
    """Re-sign / extend an own player (Bird rights — allowed over the cap).

    For the user the player must be willing (see :mod:`contract_mood`) and the salary must meet
    his ask; AI re-signings skip both."""
    ok, reason = can_extend(world, team, pid)
    if not ok:
        return False, reason
    player = world.players[pid]
    if for_user:
        from hoopsim.systems import contract_mood
        mood = contract_mood.assess(world, player)
        if mood["level"] == contract_mood.TESTING_FA:
            return False, contract_mood.describe(player.short_name, mood)
        ask = extension_offer(world, player, for_user=True)[0]
        if salary < ask:
            return False, f"{player.short_name} wants about ${ask / 1_000_000:.1f}M per year."
    salary = max(VETERAN_MINIMUM, salary)        # a contract can't be below the minimum
    max_sal = max_salary(player.experience, world.salary_cap)
    if salary > max_sal:
        return False, f"Above the maximum salary ({max_sal // 1_000_000}M)."
    add_years = min(add_years, MAX_CONTRACT_YEARS - player.contract.years_remaining)
    if add_years <= 0:
        return False, "No additional years available."
    player.contract.salaries.extend([salary] * add_years)
    player.contract.guaranteed.extend([True] * add_years)
    return True, f"Extended {add_years} year(s) at ${salary / 1_000_000:.1f}M."


def grow_cap(world: World, rate: float) -> None:
    """Grow the live cap, tax line, and apron by ``rate`` (called each NBA offseason)."""
    world.salary_cap = int(world.salary_cap * (1 + rate))
    world.luxury_tax_line = int(world.luxury_tax_line * (1 + rate))
    world.first_apron = int(world.first_apron * (1 + rate))


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
        if team.mle_used:
            return False, "Over the cap — mid-level exception already used this offseason."
        return True, "Mid-level exception."
    return False, "Not enough cap space."


def uses_exception(world: World, team: Team, salary: int) -> bool:
    """True if signing at ``salary`` would dip into the mid-level exception (over the cap,
    above the minimum, and not covered by cap space) — i.e. it consumes the team's one MLE."""
    return (salary > VETERAN_MINIMUM and salary > cap_space(world, team))
