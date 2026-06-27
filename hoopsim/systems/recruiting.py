"""High-school recruiting for college mode.

Each program competes for recruits; the pull a program exerts depends on its prestige plus the
incentive offered — a scholarship + active interest (scholarship mode) or NIL money and the
recruit's marketability (NIL mode). Top recruits decide first, so blue bloods fill up and lesser
programs land the next tier — unless you actively recruit (or out-bid in NIL).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from hoopsim.gen.collegegen import make_college_player
from hoopsim.gen.namegen import NameGenerator
from hoopsim.models.contract import flat_contract
from hoopsim.models.team import Team, auto_set_lineup
from hoopsim.models.world import World
from hoopsim.systems import collegefin

ACTIVE_INTEREST_BONUS = 6.0


def _pull(world: World, team: Team, recruit, *, user_offered: bool, nil_offer: Optional[int]
          ) -> float:
    base = team.prestige * 2.0
    noise = world.rng.gauss(0.0, 2.0)
    if world.college_economy == "nil":
        nil_component = (nil_offer or 0) / 250_000.0
        market_synergy = recruit.ratings["marketability"] / 40.0
        return base * 0.7 + nil_component + market_synergy + noise
    # scholarship economy
    return base + (ACTIVE_INTEREST_BONUS if user_offered else 0.0) + noise


def ai_nil_offer(world: World, team: Team, recruit) -> int:
    budget = collegefin.nil_available(world, team)
    value = recruit.scouted_potential()
    bid = int(max(0, (value - 50)) * 40_000 * (team.prestige / 3.0))
    return min(budget, bid)


def _commit(world: World, team: Team, recruit, nil_offer: Optional[int]) -> None:
    recruit.class_year = 1
    recruit.college = team.full_name
    recruit.team_id = team.tid
    team.add_player(recruit.pid)
    if world.college_economy == "nil" and nil_offer:
        recruit.contract = flat_contract(nil_offer, 1, world.season_year)
        recruit.brand_value += nil_offer // 4
    if recruit.pid in world.recruits:
        world.recruits.remove(recruit.pid)


def resolve_recruiting(world: World, user_offers: Dict[int, object]) -> dict:
    """Sign every recruit to the program that pulls hardest. ``user_offers`` maps a recruit pid
    to True (scholarship offer) or an int (NIL amount) for the user's program."""
    user_tid = world.user_team_id
    recruits = sorted(world.recruit_players(),
                      key=lambda p: p.scouted_potential(), reverse=True)
    user_signings: List[int] = []
    total = 0
    for recruit in recruits:
        candidates = [t for t in world.team_list() if collegefin.has_roster_room(t)]
        if not candidates:
            break
        best_team = None
        best_pull = -1e9
        best_offer = None
        for team in candidates:
            is_user = team.tid == user_tid
            if world.college_economy == "nil":
                offer = (user_offers.get(recruit.pid) if is_user
                         else ai_nil_offer(world, team, recruit))
                offer = int(offer) if offer else 0
                pull = _pull(world, team, recruit, user_offered=False, nil_offer=offer)
            else:
                user_offered = bool(is_user and user_offers.get(recruit.pid))
                offer = None
                pull = _pull(world, team, recruit, user_offered=user_offered, nil_offer=None)
            if pull > best_pull:
                best_pull, best_team, best_offer = pull, team, offer
        if best_team is not None:
            _commit(world, best_team, recruit, best_offer)
            total += 1
            if best_team.tid == user_tid:
                user_signings.append(recruit.pid)
    # recruits who didn't commit leave the pool (a fresh class is generated next offseason)
    world.recruits = []
    for team in world.team_list():
        auto_set_lineup(team, world.players)
    return {"user_signings": user_signings, "total": total}


def fill_college_rosters(world: World, minimum: int = 11) -> int:
    """Top up any thin program with generated walk-on freshmen so it can field a team."""
    names = NameGenerator(world.rng)
    added = 0
    for team in world.team_list():
        while len(team.roster) < minimum:
            target = int(max(44, min(58, round(world.rng.gauss(50, 4)))))
            p = make_college_player(world, names, team, 1, target)
            p.redshirt = False
            world.add_player(p)
            team.add_player(p.pid)
            added += 1
        auto_set_lineup(team, world.players)
    return added
