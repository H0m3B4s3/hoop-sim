"""Free-agent market: market valuation, AI signings, and a user-facing sign helper."""
from __future__ import annotations

from typing import List, Tuple

from hoopr.config import VETERAN_MINIMUM
from hoopr.models.contract import flat_contract
from hoopr.models.player import Player
from hoopr.models.team import Team, auto_set_lineup
from hoopr.models.world import World
from hoopr.systems import cap

TARGET_ROSTER = 14


def contract_years_for(player: Player) -> int:
    if player.age < 30:
        return 3
    if player.age < 33:
        return 2
    return 1


def offer_for(world: World, team: Team, player: Player) -> Tuple[int, int]:
    """The (salary, years) it takes to sign this free agent — their market price.

    A free agent commands their market value; a capped-out team simply may not be able to fit it
    (that legality is enforced in :func:`sign_free_agent`). The price is *not* silently reduced to
    the minimum — you can't land a star for a veteran-minimum deal.
    """
    return max(VETERAN_MINIMUM, cap.market_salary(player)), contract_years_for(player)


def sign_free_agent(world: World, team: Team, pid: int, salary: int, years: int
                    ) -> Tuple[bool, str]:
    """Sign a free agent to a contract after checking the player accepts and it is cap-legal."""
    player = world.players[pid]
    if player.team_id is not None:
        return False, "Player is not a free agent."
    asking = cap.market_salary(player)
    if salary < asking:
        return False, f"{player.short_name} won't sign for that — they want about " \
                      f"${asking // 1_000_000}M."
    ok, reason = cap.can_sign(world, team, salary)
    if not ok:
        return False, reason
    world.sign_player(pid, team.tid, flat_contract(salary, years, world.season_year))
    auto_set_lineup(team, world.players)
    return True, reason


def run_free_agency(world: World) -> dict:
    """AI teams sign available free agents to fill needs within their cap. User is excluded."""
    ai_teams = [t for t in world.team_list() if t.tid != world.user_team_id]
    free = sorted(world.free_agents, key=lambda pid: world.players[pid].overall, reverse=True)
    signings = 0
    for pid in free:
        player = world.players[pid]
        salary = cap.market_salary(player)
        years = contract_years_for(player)
        candidates: List[Team] = [t for t in ai_teams if len(t.roster) < TARGET_ROSTER
                                  and cap.can_sign(world, t, salary)[0]]
        if not candidates:
            continue
        team = max(candidates, key=lambda t: cap.cap_space(world, t))
        world.sign_player(pid, team.tid, flat_contract(salary, years, world.season_year))
        signings += 1
    for t in ai_teams:
        auto_set_lineup(t, world.players)
    return {"signings": signings}
