"""Trade construction, cap-legality validation, AI evaluation, and execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from hoopr.config import ROSTER_MAX, TRADE_DEADLINE_FRACTION
from hoopr.models.league import Phase
from hoopr.models.team import Team, auto_set_lineup, roster_players
from hoopr.models.world import World
from hoopr.systems import cap

ROSTER_FLOOR_AFTER_TRADE = 12


def trade_deadline_day(world: World) -> int:
    """The last day on which trades are allowed (NBA), ~2/3 through the regular season."""
    return round(TRADE_DEADLINE_FRACTION * world.season_games)


def trade_deadline_passed(world: World) -> bool:
    """True once the NBA regular-season trade deadline is behind us (waivers still allowed)."""
    return (world.mode == "nba" and world.phase == Phase.REGULAR_SEASON
            and world.day > trade_deadline_day(world))


@dataclass
class TradeOffer:
    a: int                       # team A id (typically the user)
    b: int                       # team B id
    a_sends: List[int] = field(default_factory=list)   # pids A gives to B
    b_sends: List[int] = field(default_factory=list)   # pids B gives to A


def _salary(world: World, pids: List[int]) -> int:
    return sum(world.players[pid].contract.current_salary for pid in pids)


def validate_trade(world: World, offer: TradeOffer) -> Tuple[bool, str]:
    if trade_deadline_passed(world):
        return False, "The trade deadline has passed."
    a, b = world.teams[offer.a], world.teams[offer.b]
    if not offer.a_sends and not offer.b_sends:
        return False, "Empty trade."
    if any(pid not in a.roster for pid in offer.a_sends):
        return False, "A player is not on the first team."
    if any(pid not in b.roster for pid in offer.b_sends):
        return False, "A player is not on the second team."

    # A sends out_a and receives in_a; B is the mirror.
    out_a, in_a = _salary(world, offer.a_sends), _salary(world, offer.b_sends)
    out_b, in_b = in_a, out_a
    space_a, space_b = cap.cap_space(world, a), cap.cap_space(world, b)
    if not cap.trade_matching_ok(space_a, out_a, in_a):
        return False, f"{a.abbrev} cannot match salary (incoming too large)."
    if not cap.trade_matching_ok(space_b, out_b, in_b):
        return False, f"{b.abbrev} cannot match salary (incoming too large)."

    size_a = len(a.roster) - len(offer.a_sends) + len(offer.b_sends)
    size_b = len(b.roster) - len(offer.b_sends) + len(offer.a_sends)
    for team, size in ((a, size_a), (b, size_b)):
        if size > ROSTER_MAX:
            return False, f"{team.abbrev} would exceed the roster maximum."
        if size < ROSTER_FLOOR_AFTER_TRADE:
            return False, f"{team.abbrev} would fall below the roster floor."
    return True, "Trade is legal."


def ai_evaluates(world: World, offer: TradeOffer, ai_tid: int) -> Tuple[bool, str]:
    """Decide whether the AI team ``ai_tid`` accepts the offer."""
    legal, reason = validate_trade(world, offer)
    if not legal:
        return False, reason
    if ai_tid == offer.a:
        incoming, outgoing = offer.b_sends, offer.a_sends
    else:
        incoming, outgoing = offer.a_sends, offer.b_sends
    v_in = sum(cap.trade_value(world.players[pid]) for pid in incoming)
    v_out = sum(cap.trade_value(world.players[pid]) for pid in outgoing)
    if v_in >= v_out * 1.03:
        return True, "The deal improves our team."
    if v_in >= v_out * 0.97:
        return False, "We'd want a bit more value to do this."
    return False, "That's too lopsided for us."


TRADE_BLOCK_VET_AGE = 30
TRADE_BLOCK_MAX_YEARS = 2   # last one or two years of the deal


def team_trade_block(world: World, team: Team) -> List[int]:
    """Players ``team`` is shopping — its trade-block "for sale" list, computed on demand.

    A team out of contention sells its aging veterans on expiring deals: a club is a seller
    when it is below .500 (or, in the preseason, projects as a non-contender by prestige), and
    it dangles players who are ``TRADE_BLOCK_VET_AGE``+ and in the last one or two years of
    their contract. Contenders hold everyone. Returned high-overall first for display.
    """
    contending = team.win_pct >= 0.5 if team.games_played else team.prestige >= 4
    if contending:
        return []
    block = [p.pid for p in roster_players(team, world.players)
             if p.age >= TRADE_BLOCK_VET_AGE
             and 0 < p.contract.years_remaining <= TRADE_BLOCK_MAX_YEARS
             and cap.trade_value(p) > 0]
    block.sort(key=lambda pid: world.players[pid].overall, reverse=True)
    return block


def execute_trade(world: World, offer: TradeOffer) -> None:
    a, b = world.teams[offer.a], world.teams[offer.b]
    for pid in list(offer.a_sends):
        world.transfer_player(pid, b.tid)
    for pid in list(offer.b_sends):
        world.transfer_player(pid, a.tid)
    auto_set_lineup(a, world.players)
    auto_set_lineup(b, world.players)
