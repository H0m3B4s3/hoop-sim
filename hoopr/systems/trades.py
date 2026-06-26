"""Trade construction, cap-legality validation, AI evaluation, and execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from hoopr.config import ROSTER_MAX
from hoopr.models.team import auto_set_lineup
from hoopr.models.world import World
from hoopr.systems import cap

ROSTER_FLOOR_AFTER_TRADE = 12


@dataclass
class TradeOffer:
    a: int                       # team A id (typically the user)
    b: int                       # team B id
    a_sends: List[int] = field(default_factory=list)   # pids A gives to B
    b_sends: List[int] = field(default_factory=list)   # pids B gives to A


def _salary(world: World, pids: List[int]) -> int:
    return sum(world.players[pid].contract.current_salary for pid in pids)


def validate_trade(world: World, offer: TradeOffer) -> Tuple[bool, str]:
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


def execute_trade(world: World, offer: TradeOffer) -> None:
    a, b = world.teams[offer.a], world.teams[offer.b]
    for pid in list(offer.a_sends):
        world.transfer_player(pid, b.tid)
    for pid in list(offer.b_sends):
        world.transfer_player(pid, a.tid)
    auto_set_lineup(a, world.players)
    auto_set_lineup(b, world.players)
