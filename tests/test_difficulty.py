"""Front-office difficulty moves how hard the league bargains with the user, and nothing else."""
from __future__ import annotations

import pytest

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.team import roster_players
from hoopsim.models.world import World
from hoopsim.sim.season import start_season
from hoopsim.systems import cap, freeagency, trades
from hoopsim.systems.trades import TradeOffer, ai_evaluates, execute_trade, solicit_offers

LEVELS = ("easy", "normal", "hard")


def _world(seed=1, level="normal"):
    w = build_world(seed=seed, season_preset="Standard")
    w.user_team_id = w.team_list()[0].tid
    w.difficulty = level
    start_season(w)
    return w


def test_normal_is_the_plain_market():
    w = _world()
    assert trades.accept_margin(w, True) == trades.ACCEPT_MARGIN
    fa = w.free_agent_players()[0]
    assert freeagency.offer_for(w, w.user_team, fa)[0] == freeagency.wave_market_salary(w, fa)
    assert freeagency.required_salary(w, fa, 2, for_user=True) == freeagency.required_salary(w, fa, 2)


def test_harder_levels_raise_the_bar_for_user_trades_only():
    margins = {lvl: trades.accept_margin(_world(level=lvl), True) for lvl in LEVELS}
    assert margins["easy"] < margins["normal"] < margins["hard"]
    # Easy stays above fair value, so a deal the AI loses on is never accepted
    assert margins["easy"] > 1.0
    for lvl in LEVELS:
        assert trades.accept_margin(_world(level=lvl), False) == trades.ACCEPT_MARGIN


def test_shopping_a_player_returns_less_on_harder_levels():
    totals = {}
    for lvl in LEVELS:
        w = _world(level=lvl)
        totals[lvl] = 0.0
        for p in roster_players(w.user_team, w.players):
            offers = solicit_offers(w, [p.pid])
            for so in offers:
                assert ai_evaluates(w, so.offer, so.offer.b)[0]     # still clears the AI's own bar
            totals[lvl] += offers[0].value if offers else 0.0
    assert totals["easy"] > totals["normal"] > totals["hard"]


def test_selling_then_buying_back_still_never_profits_on_easy():
    checked = 0
    for seed in (1, 2):
        w = _world(seed, "easy")
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
    assert checked > 10


def test_league_run_trades_ignore_difficulty():
    deals = {}
    for lvl in LEVELS:
        w = _world(level=lvl)
        for i, team in enumerate(w.team_list()):             # half the league contending
            team.wins, team.losses = (28, 12) if i % 2 else (12, 28)
        sellers = [t for t in w.team_list() if t.tid != w.user_team_id]
        found = []
        for seller in sellers:
            for pid in trades.team_trade_block(w, seller):
                offer = trades._ai_deal_for(w, seller, pid)
                if offer is not None:
                    found.append((offer.a, offer.b, offer.a_sends, offer.b_sends, offer.b_picks))
        deals[lvl] = found
    assert deals["normal"]
    assert deals["easy"] == deals["normal"] == deals["hard"]


def test_free_agents_and_extensions_ask_the_user_more_on_hard():
    asks, ext, ai_ext = {}, {}, set()
    for lvl in LEVELS:
        w = _world(level=lvl)
        fa = max(w.free_agent_players(), key=lambda p: p.overall)
        asks[lvl] = freeagency.offer_for(w, w.user_team, fa)[0]
        # AI teams pay the plain market price at every level
        assert freeagency.offer_for(w, w.team_list()[1], fa)[0] == freeagency.wave_market_salary(w, fa)
        star = max(roster_players(w.user_team, w.players), key=lambda p: cap.market_salary(p))
        ext[lvl] = cap.extension_offer(w, star, for_user=True)[0]
        ai_ext.add(cap.extension_offer(w, star)[0])
    assert asks["easy"] < asks["normal"] < asks["hard"]
    assert ext["easy"] <= ext["normal"] <= ext["hard"] and ext["easy"] < ext["hard"]
    assert len(ai_ext) == 1 and ext["normal"] in ai_ext     # AI re-signings never move
    # the normal asking price no longer gets a deal done on hard
    w = _world(level="hard")
    fa = max(w.free_agent_players(), key=lambda p: p.overall)
    years = freeagency.contract_years_for(fa)
    normal_price = freeagency.required_salary(w, fa, years)
    assert not freeagency.evaluate_offer(w, fa, normal_price, years, for_user=True)[0]
    assert freeagency.evaluate_offer(w, fa, normal_price, years)[0]


def test_difficulty_survives_a_save_and_old_saves_default_to_normal():
    w = _world(level="hard")
    assert World.from_dict(w.to_dict()).difficulty == "hard"
    d = w.to_dict()
    d.pop("difficulty")
    assert World.from_dict(d).difficulty == "normal"


def test_api_sets_difficulty_at_creation_and_mid_career(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from hoopsim.web.app import app
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)
    state = client.post("/api/career/new", json={"league": "nba", "preset": "Quick", "seed": 3,
                                                 "difficulty": "hard"}).json()
    assert state["summary"]["difficulty"] == "hard"
    client.post(f"/api/career/team/{state['summary']['teams'][0]['tid']}")
    r = client.post("/api/difficulty", json={"level": "easy"})
    assert r.status_code == 200 and r.json()["summary"]["difficulty"] == "easy"
    assert client.post("/api/difficulty", json={"level": "insane"}).status_code == 400
