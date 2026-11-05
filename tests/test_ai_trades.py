"""AI clubs trade with each other: sellers move veterans to contenders before the deadline."""
from __future__ import annotations

from collections import Counter

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.world import World
from hoopsim.sim import season as S
from hoopsim.systems import trades
from hoopsim.systems.trades import ai_evaluates, team_trade_block

SEEDS = (1, 2, 3)


def _world(seed):
    w = build_world(seed=seed, season_preset="Quick")
    w.user_team_id = w.team_list()[0].tid
    S.start_season(w)
    return w


def _league_trades(world, since):
    return [n for n in world.news[since:] if n.category == "transaction" and " trade " in n.headline]


def _played_season(seed):
    w = _world(seed)
    start = len(w.news)
    while not S.regular_season_complete(w):
        S.advance_one_day(w)
    return w, _league_trades(w, start)


def test_ai_clubs_trade_with_each_other_inside_the_window():
    total = 0
    for seed in SEEDS:
        w, deals = _played_season(seed)
        total += len(deals)
        opens = round(w.season_games * trades.AI_TRADE_OPENS_FRACTION)
        for n in deals:
            assert opens <= n.day <= trades.trade_deadline_day(w)
            assert w.user_team_id not in n.tids
        # one league-run deal per club per season, so nobody flips what it just bought
        clubs = Counter(t for n in deals for t in n.tids)
        assert max(clubs.values(), default=0) == 1
    assert total >= len(SEEDS) * 2


def test_every_league_deal_clears_both_clubs_and_runs_seller_to_contender():
    found = 0
    for seed in SEEDS:
        w = _world(seed)
        while w.day < trades.trade_deadline_day(w) - 2:
            S.advance_one_day(w)
        for seller in w.team_list():
            if not trades._ai_ready(w, seller):
                continue
            for pid in team_trade_block(w, seller):
                offer = trades._ai_deal_for(w, seller, pid)
                if offer is None:
                    continue
                found += 1
                buyer = w.teams[offer.b]
                assert offer.a == seller.tid and offer.a_sends == [pid]
                assert not trades._contending(seller) and trades._contending(buyer)
                assert w.user_team_id not in (offer.a, offer.b)
                assert ai_evaluates(w, offer, seller.tid)[0]
                assert ai_evaluates(w, offer, buyer.tid)[0]
    assert found >= 5


def test_no_league_deals_after_the_deadline_or_in_college():
    w = _world(1)
    w.day = trades.trade_deadline_day(w) + 1
    assert all(trades.run_ai_trades(w) == 0 for _ in range(50))
    w.day, w.mode = trades.trade_deadline_day(w) - 1, "college"
    assert all(trades.run_ai_trades(w) == 0 for _ in range(50))


def test_old_saves_without_cooldowns_still_load():
    w = _world(1)
    d = w.to_dict()
    d.pop("ai_trade_cooldowns")
    assert World.from_dict(d).ai_trade_cooldowns == {}
    w.ai_trade_cooldowns = {w.team_list()[3].tid: 40}
    assert World.from_dict(w.to_dict()).ai_trade_cooldowns == w.ai_trade_cooldowns


def test_cooldowns_reset_with_the_new_season():
    w = _world(1)
    w.ai_trade_cooldowns = {w.team_list()[3].tid: 40}
    w.offer_cooldowns = {next(iter(w.players)): 40}
    S.start_season(w)
    assert w.ai_trade_cooldowns == {} and w.offer_cooldowns == {}


def test_a_picks_only_return_does_not_read_as_cash():
    from hoopsim.systems import news
    w = _world(1)
    a, b = w.team_list()[1], w.team_list()[2]
    vet = w.players[a.roster[0]]
    news.trade(w, a, b, [vet], [], 0, 1)
    assert w.news[-1].detail == f"{b.full_name} send 1 pick the other way."
