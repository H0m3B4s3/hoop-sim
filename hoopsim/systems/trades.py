"""Trade construction, cap-legality validation, AI evaluation, and execution."""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from hoopsim.config import ROSTER_MAX, TRADE_DEADLINE_FRACTION
from hoopsim.models.league import Phase
from hoopsim.models.team import Team, auto_set_lineup, roster_players
from hoopsim.models.world import World
from hoopsim.systems import cap

ROSTER_FLOOR_AFTER_TRADE = 12


def trade_deadline_day(world: World) -> int:
    """The last day on which trades are allowed (NBA), ~2/3 through the regular season."""
    return round(TRADE_DEADLINE_FRACTION * world.season_games)


def trade_deadline_passed(world: World) -> bool:
    """True once the NBA regular-season trade deadline is behind us (waivers still allowed)."""
    return (world.mode == "nba" and world.phase == Phase.REGULAR_SEASON
            and world.day > trade_deadline_day(world))


# A pick reference is its identity key: (year, round, original_tid).
PickKey = Tuple[int, int, int]


@dataclass
class TradeOffer:
    a: int                       # team A id (typically the user)
    b: int                       # team B id
    a_sends: List[int] = field(default_factory=list)        # pids A gives to B
    b_sends: List[int] = field(default_factory=list)        # pids B gives to A
    a_picks: List[PickKey] = field(default_factory=list)    # picks A gives to B
    b_picks: List[PickKey] = field(default_factory=list)    # picks B gives to A


def _salary(world: World, pids: List[int]) -> int:
    return sum(world.players[pid].contract.current_salary for pid in pids)


def _picks_value(world: World, keys: List[PickKey]) -> float:
    total = 0.0
    for key in keys:
        pick = world.find_pick(*key)
        if pick is not None:
            total += cap.pick_value(world, pick)
    return total


def validate_trade(world: World, offer: TradeOffer) -> Tuple[bool, str]:
    if trade_deadline_passed(world):
        return False, "The trade deadline has passed."
    a, b = world.teams[offer.a], world.teams[offer.b]
    if not (offer.a_sends or offer.b_sends or offer.a_picks or offer.b_picks):
        return False, "Empty trade."
    if any(pid not in a.roster for pid in offer.a_sends):
        return False, "A player is not on the first team."
    if any(pid not in b.roster for pid in offer.b_sends):
        return False, "A player is not on the second team."
    for key in offer.a_picks:
        pk = world.find_pick(*key)
        if pk is None or pk.owner_tid != a.tid:
            return False, f"{a.abbrev} no longer controls one of those picks."
    for key in offer.b_picks:
        pk = world.find_pick(*key)
        if pk is None or pk.owner_tid != b.tid:
            return False, f"{b.abbrev} no longer controls one of those picks."

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


# ---------------------------------------------------------------------------
# How an AI team sizes up a deal
# ---------------------------------------------------------------------------
ACCEPT_MARGIN = 1.03        # incoming worth must beat outgoing by this much for a yes
CLOSE_MARGIN = 0.97         # within this much, the AI says it wants a bit more
# Roster spots are finite, so each extra incoming player counts for less than the one before.
PIECE_WEIGHTS = (1.0, 0.75, 0.5, 0.35)
# A team pays extra to keep the young star it is built around.
FRANCHISE_PREMIUM = 1.25
FRANCHISE_MAX_AGE = 29
# Rebuilders discount veterans and prize picks; contenders will spend picks to win now.
TRADE_BLOCK_VET_AGE = 30
REBUILDER_VET_FACTOR = 0.75
REBUILDER_PICK_FACTOR = 1.2
CONTENDER_PICK_FACTOR = 0.85


def _contending(team: Team) -> bool:
    """Whether a club is playing for now: a winning record, or prestige before games are played."""
    return team.win_pct >= 0.5 if team.games_played else team.prestige >= 4


def _player_worth(team: Team, player) -> float:
    """What a player is worth to this team, given where it is in its cycle."""
    value = cap.trade_value(player)
    if value > 0 and player.age >= TRADE_BLOCK_VET_AGE and not _contending(team):
        value *= REBUILDER_VET_FACTOR
    return value


def _pick_worth(world: World, team: Team, pick) -> float:
    factor = CONTENDER_PICK_FACTOR if _contending(team) else REBUILDER_PICK_FACTOR
    return cap.pick_value(world, pick) * factor


def _picks_worth(world: World, team: Team, keys: List[PickKey]) -> float:
    picks = (world.find_pick(*key) for key in keys)
    return sum(_pick_worth(world, team, pick) for pick in picks if pick is not None)


def _franchise_player(world: World, team: Team) -> Optional[int]:
    """The young star this team is built around, if it has one."""
    players = roster_players(team, world.players)
    if not players:
        return None
    best = max(players, key=lambda p: cap.trade_value(p))
    return best.pid if best.age <= FRANCHISE_MAX_AGE else None


def _incoming_worth(world: World, team: Team, pids: List[int], picks: List[PickKey]) -> float:
    """Worth of what ``team`` would receive. Liabilities always count in full."""
    worths = sorted((_player_worth(team, world.players[pid]) for pid in pids), reverse=True)
    total = _picks_worth(world, team, picks)
    for i, worth in enumerate(worths):
        total += worth * PIECE_WEIGHTS[min(i, len(PIECE_WEIGHTS) - 1)] if worth > 0 else worth
    return total


def _outgoing_worth(world: World, team: Team, pids: List[int], picks: List[PickKey]) -> float:
    """Worth of what ``team`` would give up, including the premium on its franchise player."""
    total = sum(_player_worth(team, world.players[pid]) for pid in pids)
    franchise = _franchise_player(world, team)
    if franchise in pids:
        total += _player_worth(team, world.players[franchise]) * (FRANCHISE_PREMIUM - 1)
    return total + _picks_worth(world, team, picks)


def ai_evaluates(world: World, offer: TradeOffer, ai_tid: int) -> Tuple[bool, str]:
    """Decide whether the AI team ``ai_tid`` accepts the offer."""
    legal, reason = validate_trade(world, offer)
    if not legal:
        return False, reason
    if ai_tid == offer.a:
        in_pids, out_pids = offer.b_sends, offer.a_sends
        in_picks, out_picks = offer.b_picks, offer.a_picks
    else:
        in_pids, out_pids = offer.a_sends, offer.b_sends
        in_picks, out_picks = offer.a_picks, offer.b_picks
    team = world.teams[ai_tid]
    v_in = _incoming_worth(world, team, in_pids, in_picks)
    v_out = _outgoing_worth(world, team, out_pids, out_picks)
    if v_in >= v_out * ACCEPT_MARGIN:
        return True, "The deal improves our team."
    if v_in >= v_out * CLOSE_MARGIN:
        return False, "We'd want a bit more value to do this."
    if _franchise_player(world, team) in out_pids:
        return False, "We're building around him. It would take a franchise-changing offer."
    if len(in_pids) > 1 and v_out > 0:
        return False, "We'd rather have one real piece than several decent ones."
    return False, "That's too lopsided for us."


TRADE_BLOCK_MAX_YEARS = 2   # last one or two years of the deal


def team_trade_block(world: World, team: Team) -> List[int]:
    """Players ``team`` is shopping — its trade-block "for sale" list, computed on demand.

    A team out of contention sells its aging veterans on expiring deals: a club is a seller
    when it is below .500 (or, in the preseason, projects as a non-contender by prestige), and
    it dangles players who are ``TRADE_BLOCK_VET_AGE``+ and in the last one or two years of
    their contract. Contenders hold everyone. Returned high-overall first for display.
    """
    if _contending(team):
        return []
    block = [p.pid for p in roster_players(team, world.players)
             if p.age >= TRADE_BLOCK_VET_AGE
             and 0 < p.contract.years_remaining <= TRADE_BLOCK_MAX_YEARS
             and cap.trade_value(p) > 0]
    block.sort(key=lambda pid: world.players[pid].overall, reverse=True)
    return block


# ---------------------------------------------------------------------------
# Soliciting offers — the user shops their own player(s) around the league
# ---------------------------------------------------------------------------
# An AI team only offers what it would accept itself, so the top of the range is the most it
# can pay and still clear ACCEPT_MARGIN. Below this floor it isn't a serious offer.
OFFER_VALUE_FLOOR = 0.85
OFFER_CHIP_POOL = 14        # candidate tradeable pieces per team considered for packages
OFFER_MAX_PIECES = 3        # at most this many players come back in one offer


@dataclass
class SolicitedOffer:
    offer: TradeOffer
    value: float                 # total trade value coming back to the user
    target_value: float          # value of the player(s) the user is shopping


def _team_wants(world: World, team: Team, targets: List[int]) -> bool:
    """Whether ``team`` is interested in acquiring the shopped player(s).

    A team bites if the best target would crack its rotation (roughly upgrade its
    eighth man) — contenders chase win-now talent, rebuilders chase young upside.
    """
    best = max(world.players[pid].overall for pid in targets)
    overalls = sorted((p.overall for p in roster_players(team, world.players)), reverse=True)
    bar = overalls[7] if len(overalls) > 7 else (overalls[-1] if overalls else 0)
    return best >= bar - 2


@dataclass
class _Chip:
    """A tradeable asset in package-building: a player or a draft pick."""
    value: float
    salary: int
    is_player: bool
    ref: object        # pid (int) for players, PickKey (tuple) for picks


def _team_chips(world: World, team: Team, buying: float) -> List[_Chip]:
    """The assets ``team`` would consider parting with, best value first, pool-capped.

    Players plus the team's own future picks, each at what it is worth to this team. Picks let
    a contender land your veteran without gutting its rotation — the classic rebuild return.
    The franchise player is only in play when what's being bought is worth more than he is.
    """
    franchise = _franchise_player(world, team)
    chips = []
    for p in roster_players(team, world.players):
        worth = _player_worth(team, p)
        if p.pid == franchise:
            worth *= FRANCHISE_PREMIUM
            if worth >= buying:
                continue
        if worth > 0:
            chips.append(_Chip(worth, p.contract.current_salary, True, p.pid))
    chips += [_Chip(_pick_worth(world, team, pk), 0, False, pk.key)
              for pk in world.picks_owned_by(team.tid)]
    chips.sort(key=lambda c: c.value, reverse=True)
    return chips[:OFFER_CHIP_POOL]


def _best_package(world: World, team: Team, buying: float, target_salary: int,
                  partner_space: int, partner_size_base: int, n_targets: int
                  ) -> Optional[Tuple[List[int], List[PickKey]]]:
    """Assemble the best package ``team`` would send for the targets, or ``None``.

    ``buying`` is what the targets are worth to ``team``. The package costs it no more than it
    would accept in a trade, matches salary both ways, and respects both rosters' size limits.
    Among legal candidates we return the richest one (fewest assets to break ties). The partner
    is whoever owns the targets: the user, or another AI club in a league-run deal.
    """
    pool = _team_chips(world, team, buying)
    ai_space = cap.cap_space(world, team)
    lo, hi = buying * OFFER_VALUE_FLOOR, buying / ACCEPT_MARGIN

    best: Optional[Tuple[List[int], List[PickKey]]] = None
    best_score: Optional[Tuple[float, int]] = None
    for r in range(1, OFFER_MAX_PIECES + 1):
        for combo in itertools.combinations(pool, r):
            v = sum(c.value for c in combo)
            if v < lo or v > hi:
                continue
            n_players = sum(1 for c in combo if c.is_player)
            ai_size = len(team.roster) - n_players + n_targets
            partner_size = partner_size_base + n_players
            if not (ROSTER_FLOOR_AFTER_TRADE <= ai_size <= ROSTER_MAX) or partner_size > ROSTER_MAX:
                continue
            sal = sum(c.salary for c in combo)
            if not cap.trade_matching_ok(partner_space, target_salary, sal):
                continue
            if not cap.trade_matching_ok(ai_space, sal, target_salary):
                continue
            score = (v, -r)
            if best_score is None or score > best_score:
                best_score = score
                best = ([c.ref for c in combo if c.is_player],
                        [c.ref for c in combo if not c.is_player])
    return best


def solicit_offers(world: World, pids: List[int], max_offers: int = 10) -> List[SolicitedOffer]:
    """Shop the user's player(s) around: gather the offers interested teams would make.

    Returns offers (best haul first) that are cap-legal and that the AI would
    genuinely propose. Offers may include players, future draft picks, or both.
    Empty once the deadline has passed or no team bites.
    """
    user = world.user_team
    if user is None or trade_deadline_passed(world):
        return []
    targets = [pid for pid in pids if pid in user.roster]
    if not targets:
        return []
    target_value = sum(cap.trade_value(world.players[pid]) for pid in targets)
    target_salary = _salary(world, targets)
    user_space = cap.cap_space(world, user)
    user_size_base = len(user.roster) - len(targets)

    results: List[SolicitedOffer] = []
    for team in world.team_list():
        if team.tid == user.tid or not _team_wants(world, team, targets):
            continue
        pkg = _best_package(world, team, _incoming_worth(world, team, targets, []), target_salary,
                            user_space, user_size_base, len(targets))
        if pkg is None:
            continue
        pids_back, picks_back = pkg
        offer = TradeOffer(user.tid, team.tid, list(targets), pids_back, [], picks_back)
        if not validate_trade(world, offer)[0]:
            continue
        value = (sum(cap.trade_value(world.players[p]) for p in pids_back)
                 + _picks_value(world, picks_back))
        results.append(SolicitedOffer(offer, value, target_value))
    results.sort(key=lambda o: o.value, reverse=True)
    return results[:max_offers]


def _team_wants_pick(world: World, team: Team, pick) -> bool:
    """Whether ``team`` would move to acquire the user's pick.

    Everyone covets a first-rounder; only rosters thin on youth bother trading for a second."""
    if pick.round == 1:
        return True
    young = sum(1 for p in roster_players(team, world.players) if p.age <= 23)
    return young <= 3


def solicit_pick_offers(world: World, pick_key: PickKey, max_offers: int = 8
                        ) -> List[SolicitedOffer]:
    """Shop one of the user's draft picks: gather what interested teams would give to acquire it.

    The user sends the pick (no salary) and receives players and/or picks, so deals are
    cap-constrained by the user's own space — exactly the move-down-for-assets logic teams use
    on draft night. Best haul first; empty if the user doesn't control the pick or no team bites.
    """
    user = world.user_team
    if user is None:
        return []
    pick = world.find_pick(*pick_key)
    if pick is None or pick.owner_tid != user.tid:
        return []
    target_value = cap.pick_value(world, pick)
    user_space = cap.cap_space(world, user)
    user_size_base = len(user.roster)

    results: List[SolicitedOffer] = []
    for team in world.team_list():
        if team.tid == user.tid or not _team_wants_pick(world, team, pick):
            continue
        pkg = _best_package(world, team, _pick_worth(world, team, pick), 0,
                            user_space, user_size_base, 0)
        if pkg is None:
            continue
        pids_back, picks_back = pkg
        offer = TradeOffer(user.tid, team.tid, [], pids_back, [pick_key], picks_back)
        if not validate_trade(world, offer)[0]:
            continue
        value = (sum(cap.trade_value(world.players[p]) for p in pids_back)
                 + _picks_value(world, picks_back))
        results.append(SolicitedOffer(offer, value, target_value))
    results.sort(key=lambda o: o.value, reverse=True)
    return results[:max_offers]


# ---------------------------------------------------------------------------
# AI-initiated offers — the league brings deals to the user (trade-block driven)
# ---------------------------------------------------------------------------
MAX_ACTIVE_OFFERS = 3
OFFER_LIFESPAN_DAYS = 7
OFFER_COOLDOWN_DAYS = 5
BLOCK_OFFER_DAILY_CHANCE = 0.30      # per blocked player, per user game day
UNSOLICITED_DAILY_CHANCE = 0.04      # rare league-wide interest in a star you haven't shopped
UNSOLICITED_MIN_VALUE = 14.0         # only genuine difference-makers draw unsolicited offers


def offer_to_trade(world: World, o: dict) -> TradeOffer:
    """Rebuild a ``TradeOffer`` (user perspective) from a stored offer dict."""
    return TradeOffer(world.user_team_id, o["from_tid"],
                      list(o["user_sends"]), list(o["team_sends"]),
                      [], [tuple(k) for k in o.get("team_picks", [])])


def _offer_still_valid(world: World, o: dict) -> bool:
    return validate_trade(world, offer_to_trade(world, o))[0]


def _cooldown(world: World, pids: List[int]) -> None:
    for pid in pids:
        world.offer_cooldowns[pid] = world.day + OFFER_COOLDOWN_DAYS


def _expire_offers(world: World) -> None:
    """Drop offers that have aged out or become illegal, arming a cooldown on their targets."""
    kept = []
    for o in world.trade_offers:
        if world.day > o["expires_day"] or not _offer_still_valid(world, o):
            _cooldown(world, o["user_sends"])
        else:
            kept.append(o)
    world.trade_offers = kept


def _spawn_offer(world: World, pid: int, *, unsolicited: bool) -> bool:
    """Generate and store the best available offer for one of the user's players."""
    offers = solicit_offers(world, [pid], max_offers=3)
    if not offers:
        return False
    so = world.rng.choice(offers)            # vary which suitor steps up
    o = so.offer
    world.trade_offers.append({
        "id": world.new_offer_id(),
        "from_tid": o.b,
        "user_sends": list(o.a_sends),
        "team_sends": list(o.b_sends),
        "team_picks": [list(k) for k in o.b_picks],
        "value": round(so.value, 1),
        "created_day": world.day,
        "expires_day": world.day + OFFER_LIFESPAN_DAYS,
        "unsolicited": unsolicited,
    })
    return True


def _coveted_star(world: World, user: Team, exclude: set) -> Optional[int]:
    """A high-value player the user hasn't shopped, whom a rival might chase unprompted."""
    candidates = [p.pid for p in roster_players(user, world.players)
                  if p.pid not in exclude and p.pid not in user.block_list
                  and world.offer_cooldowns.get(p.pid, 0) <= world.day
                  and cap.trade_value(p) >= UNSOLICITED_MIN_VALUE]
    if not candidates:
        return None
    return max(candidates, key=lambda pid: cap.trade_value(world.players[pid]))


def refresh_offers(world: World) -> int:
    """Advance the AI-offer inbox one user game-day. Returns how many *new* offers arrived.

    Blocked players draw steady interest; the occasional star draws an unsolicited bid. Offers
    are capped, one-per-player, cooled-down after they lapse, and all clear at the deadline.
    """
    user = world.user_team
    if user is None or world.mode != "nba":
        return 0
    _expire_offers(world)
    if trade_deadline_passed(world):
        if world.trade_offers:
            _cooldown(world, [pid for o in world.trade_offers for pid in o["user_sends"]])
        world.trade_offers = []
        return 0

    pending = {pid for o in world.trade_offers for pid in o["user_sends"]}
    new = 0

    def ready(pid: int) -> bool:
        return (pid in user.roster and pid not in pending
                and world.offer_cooldowns.get(pid, 0) <= world.day)

    for pid in list(user.block_list):
        if len(world.trade_offers) >= MAX_ACTIVE_OFFERS:
            break
        if ready(pid) and world.rng.chance(BLOCK_OFFER_DAILY_CHANCE) and \
                _spawn_offer(world, pid, unsolicited=False):
            pending.add(pid)
            new += 1

    if len(world.trade_offers) < MAX_ACTIVE_OFFERS and world.rng.chance(UNSOLICITED_DAILY_CHANCE):
        star = _coveted_star(world, user, pending)
        if star is not None and _spawn_offer(world, star, unsolicited=True):
            new += 1

    return new


def accept_offer(world: World, offer_id: int) -> Tuple[bool, str]:
    o = next((x for x in world.trade_offers if x["id"] == offer_id), None)
    if o is None:
        return False, "That offer is no longer available."
    offer = offer_to_trade(world, o)
    legal, why = validate_trade(world, offer)
    if not legal:
        world.trade_offers = [x for x in world.trade_offers if x["id"] != offer_id]
        return False, why
    execute_trade(world, offer)
    world.trade_offers = [x for x in world.trade_offers if x["id"] != offer_id]
    _expire_offers(world)                    # other offers may now be illegal — clean them up
    return True, "Trade completed."


def decline_offer(world: World, offer_id: int) -> bool:
    o = next((x for x in world.trade_offers if x["id"] == offer_id), None)
    if o is None:
        return False
    _cooldown(world, o["user_sends"])
    world.trade_offers = [x for x in world.trade_offers if x["id"] != offer_id]
    return True


# ---------------------------------------------------------------------------
# League-run trades — AI clubs deal with each other
# ---------------------------------------------------------------------------
# Sellers move their trade-block veterans to contenders, mostly in the run-up to the deadline.
# Both sides must clear their own ACCEPT_MARGIN; the deal exists because a rebuilder discounts
# veterans and prizes picks while a contender does the opposite.
AI_TRADE_OPENS_FRACTION = 0.2       # records mean little before a fifth of the season is played
AI_TRADE_DAILY_CHANCE = 0.15
# The run-up to the deadline is the busy season: the final week of an 82-game schedule, scaled.
AI_TRADE_DEADLINE_RUSH_FRACTION = 0.085
AI_TRADE_DEADLINE_CHANCE = 0.6
AI_TRADE_SUITORS = 3                # the seller takes one of its best few offers
# One league-run deal per club per season, so a contender never flips the veteran it just bought.


def _ai_ready(world: World, team: Team) -> bool:
    return (team.tid != world.user_team_id
            and world.ai_trade_cooldowns.get(team.tid, 0) <= world.day)


def _ai_deal_for(world: World, seller: Team, pid: int) -> Optional[TradeOffer]:
    """A deal for one of ``seller``'s players that it and some contender would both sign off on."""
    salary = world.players[pid].contract.current_salary
    seller_space = cap.cap_space(world, seller)
    deals = []
    for buyer in world.team_list():
        if (buyer.tid == seller.tid or not _ai_ready(world, buyer) or not _contending(buyer)
                or not _team_wants(world, buyer, [pid])):
            continue
        pkg = _best_package(world, buyer, _incoming_worth(world, buyer, [pid], []), salary,
                            seller_space, len(seller.roster) - 1, 1)
        if pkg is None:
            continue
        offer = TradeOffer(seller.tid, buyer.tid, [pid], pkg[0], [], pkg[1])
        if ai_evaluates(world, offer, seller.tid)[0] and ai_evaluates(world, offer, buyer.tid)[0]:
            deals.append((_incoming_worth(world, seller, pkg[0], pkg[1]), offer))
    if not deals:
        return None
    deals.sort(key=lambda d: d[0], reverse=True)
    return world.rng.choice(deals[:AI_TRADE_SUITORS])[1]


def run_ai_trades(world: World) -> int:
    """Give the league a chance to make one AI-to-AI trade today. Returns trades made (0 or 1).

    Call once per regular-season day. Never touches the user's team.
    """
    if (world.mode != "nba" or world.phase != Phase.REGULAR_SEASON
            or trade_deadline_passed(world)
            or world.day < round(world.season_games * AI_TRADE_OPENS_FRACTION)):
        return 0
    rush = max(1, round(world.season_games * AI_TRADE_DEADLINE_RUSH_FRACTION))
    late = trade_deadline_day(world) - world.day < rush
    if not world.rng.chance(AI_TRADE_DEADLINE_CHANCE if late else AI_TRADE_DAILY_CHANCE):
        return 0
    sellers = [t for t in world.team_list() if _ai_ready(world, t) and team_trade_block(world, t)]
    if not sellers:
        return 0
    seller = world.rng.choice(sellers)
    for pid in team_trade_block(world, seller):
        offer = _ai_deal_for(world, seller, pid)
        if offer is not None:
            execute_trade(world, offer)
            for tid in (offer.a, offer.b):
                world.ai_trade_cooldowns[tid] = trade_deadline_day(world) + 1
            return 1
    return 0


def execute_trade(world: World, offer: TradeOffer) -> None:
    a, b = world.teams[offer.a], world.teams[offer.b]
    for pid in list(offer.a_sends):
        world.transfer_player(pid, b.tid)
    for pid in list(offer.b_sends):
        world.transfer_player(pid, a.tid)
    for key in list(offer.a_picks):
        pick = world.find_pick(*key)
        if pick is not None:
            pick.owner_tid = b.tid
    for key in list(offer.b_picks):
        pick = world.find_pick(*key)
        if pick is not None:
            pick.owner_tid = a.tid
    # players who changed hands can't stay on their old team's trade block
    a.block_list = [pid for pid in a.block_list if pid in a.roster]
    b.block_list = [pid for pid in b.block_list if pid in b.roster]
    auto_set_lineup(a, world.players)
    auto_set_lineup(b, world.players)
    # Emit the trade to the news wire
    from hoopsim.systems import news
    a_out = [world.players[pid] for pid in offer.a_sends]
    b_out = [world.players[pid] for pid in offer.b_sends]
    news.trade(world, a, b, a_out, b_out, len(offer.a_picks), len(offer.b_picks))
