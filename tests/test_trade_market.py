"""The trade market prices stars, upside and contracts sensibly, and can't be farmed for value."""
from __future__ import annotations

import itertools

import pytest

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.contract import flat_contract
from hoopsim.models.team import roster_players
from hoopsim.sim.season import start_season
from hoopsim.systems import cap, trades
from hoopsim.systems.trades import TradeOffer, ai_evaluates, execute_trade, solicit_offers

SEEDS = (1, 2, 3)


def _world(seed):
    w = build_world(seed=seed, season_preset="Standard")
    w.user_team_id = w.team_list()[0].tid
    start_season(w)
    return w


def _by_value(world, team):
    return sorted(roster_players(team, world.players), key=cap.trade_value, reverse=True)


def test_lesser_players_rarely_add_up_to_a_young_star():
    tried = bought = 0
    for seed in SEEDS:
        w = _world(seed)
        depth = _by_value(w, w.user_team)[1:10]
        for team in w.team_list():
            if team.tid == w.user_team_id:
                continue
            for star in roster_players(team, w.players):
                if star.overall < 85 or star.age > 29:
                    continue
                tried += 1
                lesser = [p.pid for p in depth if p.overall <= star.overall - 3]
                combos = itertools.chain.from_iterable(
                    itertools.combinations(lesser, n) for n in (2, 3))
                bought += any(ai_evaluates(w, TradeOffer(w.user_team_id, team.tid, list(c),
                                                         [star.pid]), team.tid)[0]
                              for c in combos)
    assert tried > 20
    assert bought / tried < 0.15


def test_ai_offers_clear_its_own_acceptance_bar():
    checked = 0
    for seed in SEEDS:
        w = _world(seed)
        for player in roster_players(w.user_team, w.players):
            for so in solicit_offers(w, [player.pid]):
                checked += 1
                assert ai_evaluates(w, so.offer, so.offer.b)[0]
    assert checked > 50


def test_selling_a_player_then_buying_him_back_never_works():
    checked = 0
    for seed in SEEDS:
        w = _world(seed)
        user = w.user_team
        for player in roster_players(user, w.players):
            offers = solicit_offers(w, [player.pid])
            if not offers:
                continue
            sold = offers[0].offer
            rebuy = TradeOffer(user.tid, sold.b, list(sold.b_sends), list(sold.a_sends),
                               list(sold.b_picks), [])
            execute_trade(w, sold)
            checked += 1
            assert not ai_evaluates(w, rebuy, sold.b)[0]
            execute_trade(w, rebuy)
    assert checked > 20


def test_a_bad_contract_costs_something_to_move():
    w = _world(1)
    user, partner = w.user_team, w.team_list()[1]
    partner.wins, partner.losses = 10, 30
    washed = min(roster_players(user, w.players), key=lambda p: p.overall)
    washed.age = 33
    washed.contract = flat_contract(30_000_000, 3, w.season_year)
    assert cap.trade_value(washed) < 0
    dump = TradeOffer(user.tid, partner.tid, [washed.pid], [])
    assert not ai_evaluates(w, dump, partner.tid)[0]
    # a sweetener makes the same dump worth taking
    keys = [pk.key for pk in w.picks_owned_by(user.tid) if pk.round == 1]
    sweetened = TradeOffer(user.tid, partner.tid, [washed.pid], [], keys)
    assert ai_evaluates(w, sweetened, partner.tid)[0]


def test_a_cheap_veteran_is_still_an_asset():
    w = _world(1)
    vet = max((p for p in w.players.values() if p.age >= 31), key=lambda p: p.overall)
    vet.contract = flat_contract(cap.market_salary(vet), 1, w.season_year)
    assert cap.trade_value(vet) > 0


def test_ai_pays_a_premium_to_keep_its_franchise_player():
    w = _world(2)
    team = next(t for t in w.team_list() if trades._franchise_player(w, t) is not None)
    franchise = trades._franchise_player(w, team)
    raw = trades._player_worth(team, w.players[franchise])
    assert trades._outgoing_worth(w, team, [franchise], []) == pytest.approx(
        raw * trades.FRANCHISE_PREMIUM)
    role = _by_value(w, team)[-1].pid
    assert trades._outgoing_worth(w, team, [role], []) == pytest.approx(
        trades._player_worth(team, w.players[role]))


def test_extra_incoming_players_count_for_less():
    w = _world(1)
    team = w.team_list()[1]
    a, b = _by_value(w, w.user_team)[1:3]
    pair = trades._incoming_worth(w, team, [a.pid, b.pid], [])
    assert pair < trades._player_worth(team, a) + trades._player_worth(team, b)
    assert pair == pytest.approx(trades._player_worth(team, a)
                                 + trades._player_worth(team, b) * trades.PIECE_WEIGHTS[1])


def test_a_liability_is_not_hidden_as_a_lesser_piece():
    w = _world(1)
    team = w.team_list()[1]
    good, washed = _by_value(w, w.user_team)[1], _by_value(w, w.user_team)[-1]
    washed.age = 33
    washed.contract = flat_contract(30_000_000, 3, w.season_year)
    worth = trades._incoming_worth(w, team, [good.pid, washed.pid], [])
    assert worth == pytest.approx(trades._player_worth(team, good) + cap.trade_value(washed))


def test_rebuilders_and_contenders_price_picks_and_veterans_differently():
    w = _world(1)
    rebuilder, contender = w.team_list()[1], w.team_list()[2]
    rebuilder.wins, rebuilder.losses = 10, 30
    contender.wins, contender.losses = 30, 10
    pick = w.picks_owned_by(w.user_team_id)[0]
    assert trades._pick_worth(w, rebuilder, pick) > trades._pick_worth(w, contender, pick)
    vet = next(p for p in w.players.values() if p.age >= 31 and cap.trade_value(p) > 0)
    assert trades._player_worth(rebuilder, vet) < trades._player_worth(contender, vet)


def test_upside_is_priced_for_the_young_only():
    w = _world(1)
    p = next(p for p in w.players.values() if p.potential < 90 and p.age >= 27)
    prime = cap.trade_value(p)
    p.potential += 8
    assert cap.trade_value(p) == pytest.approx(prime)       # past the age where it's bankable
    p.potential -= 8
    p.age = 20
    young = cap.trade_value(p)
    p.potential += 8
    assert cap.trade_value(p) > young


def test_refusing_to_sell_a_franchise_player_says_why():
    w = _world(2)
    refusals = []
    for team in w.team_list()[1:]:
        franchise = trades._franchise_player(w, team)
        for player in roster_players(w.user_team, w.players):
            offer = TradeOffer(w.user_team_id, team.tid, [player.pid], [franchise])
            if trades.validate_trade(w, offer)[0]:
                ok, why = ai_evaluates(w, offer, team.tid)
                if not ok and trades._incoming_worth(w, team, [player.pid], []) < (
                        trades._outgoing_worth(w, team, [franchise], []) * trades.CLOSE_MARGIN):
                    refusals.append(why)
    assert refusals
    assert all("building around" in why for why in refusals)
