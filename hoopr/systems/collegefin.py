"""College financial systems: scholarships (limit/allocation) and NIL (deals + brand value).

The active model is chosen at game start via ``world.college_economy`` ("scholarship" | "nil").
A college player's NIL deal is stored as their (one-year) contract, so existing contract/finance
machinery is reused; in scholarship mode contracts stay empty.
"""
from __future__ import annotations

from typing import Tuple

from hoopr.config import SCHOLARSHIP_LIMIT
from hoopr.models.contract import flat_contract
from hoopr.models.team import Team
from hoopr.models.world import World

NIL_MIN_DEAL = 10_000


# ---------------------------------------------------------------------------
# Scholarships
# ---------------------------------------------------------------------------
def scholarships_used(team: Team) -> int:
    return len(team.roster)


def scholarships_open(team: Team) -> int:
    return max(0, SCHOLARSHIP_LIMIT - len(team.roster))


def has_roster_room(team: Team) -> bool:
    return len(team.roster) < SCHOLARSHIP_LIMIT


# ---------------------------------------------------------------------------
# NIL
# ---------------------------------------------------------------------------
def nil_spent(world: World, team: Team) -> int:
    return sum(world.players[pid].contract.current_salary
               for pid in team.roster if pid in world.players)


def nil_available(world: World, team: Team) -> int:
    return max(0, team.nil_budget - nil_spent(world, team))


def offer_nil_deal(world: World, team: Team, pid: int, amount: int) -> Tuple[bool, str]:
    """Assign an annual NIL deal to a roster player (replacing any existing deal)."""
    player = world.players[pid]
    if pid not in team.roster:
        return False, "Player is not on your roster."
    current = player.contract.current_salary
    available = nil_available(world, team) + current
    if amount > available:
        return False, "Exceeds your NIL collective budget."
    player.contract = flat_contract(amount, 1, world.season_year)
    # Endorsement money lifts morale and (over time) brand value.
    player.morale = min(100, player.morale + 3)
    player.brand_value += amount // 4
    return True, "Deal signed."


def grow_brand_values(world: World) -> None:
    """Offseason brand growth from on-court production and marketability (NIL flavor)."""
    for team in world.team_list():
        for pid in team.roster:
            p = world.players[pid]
            perf = p.season.ppg * 1.5 + p.season.rpg + p.season.apg
            growth = int((perf * 4000) + (p.ratings["marketability"] * 1500))
            p.brand_value += growth


def college_economy_label(world: World) -> str:
    return "NIL" if world.college_economy == "nil" else "Scholarship"
