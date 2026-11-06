"""The Home screen's inbox flags what needs the user, and links each item to the tab that fixes it."""
from __future__ import annotations

import pytest

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.player import Injury
from hoopsim.models.team import roster_players
from hoopsim.sim import season as S
from hoopsim.systems import contract_mood, owner, trades
from hoopsim.web.home import home_view


def _world(seed=3):
    w = build_world(seed=seed, season_preset="Standard", backstory=False)
    w.user_team_id = w.team_list()[4].tid
    S.start_season(w)
    owner.begin_season(w)
    return w


def _tabs(view):
    return [(i["tab"], i["severity"]) for i in view["inbox"]]


def _best(w):
    return max(roster_players(w.user_team, w.players), key=lambda p: p.overall)


def test_a_quiet_preseason_has_a_next_game_and_little_in_the_inbox():
    w = _world()
    view = home_view(w)
    assert view["next_game"]["opponent"]["tid"] != w.user_team_id
    assert view["standing"]["rank"] >= 1 and view["recent"] == []
    assert all(tab != "offers" for tab, _ in _tabs(view))


def test_inbox_flags_offers_deadline_injury_and_roster_size():
    w = _world()
    w.day = trades.trade_deadline_day(w) - 1
    w.trade_offers = [{"id": 1, "from_tid": w.team_list()[0].tid, "user_sends": [],
                       "team_sends": [], "team_picks": [], "value": 1.0,
                       "created_day": w.day, "expires_day": w.day + 3, "unsolicited": False}]
    star = _best(w)
    star.injury = Injury("sprained ankle", 9, "moderate")
    view = home_view(w)
    tabs = _tabs(view)
    assert ("offers", "action") in tabs
    assert ("trade", "urgent") in tabs                    # a day out from the deadline
    assert any(i["tab"] == "injuries" and star.name in i["text"] for i in view["inbox"])
    # urgent items sort to the top
    order = {"urgent": 0, "action": 1, "info": 2}
    assert [order[s] for _, s in tabs] == sorted(order[s] for _, s in tabs)
    for pid in list(w.user_team.roster)[:4]:
        w.release_player(pid)
    assert ("fa", "urgent") in _tabs(home_view(w))


def test_an_expiring_player_planning_to_leave_shows_up(monkeypatch):
    w = _world()
    star = _best(w)
    star.contract.salaries = star.contract.salaries[:1]
    star.contract.guaranteed = star.contract.guaranteed[:1]
    monkeypatch.setattr(contract_mood, "assess", lambda world, p: {
        "level": contract_mood.TESTING_FA, "label": contract_mood.LABELS[contract_mood.TESTING_FA],
        "score": -1.0, "reasons": [], "ask_factor": None})
    view = home_view(w)
    assert any(i["tab"] == "finances" and star.name in i["text"] and "free agency" in i["text"]
               for i in view["inbox"])


def test_owner_pressure_is_flagged_after_the_honeymoon():
    w = _world()
    w.owner.update(seasons=1, confidence=22)
    assert ("play", "urgent") in _tabs(home_view(w))
    w.owner.update(seasons=0)
    assert all(tab != "play" for tab, _ in _tabs(home_view(w)))


def test_results_and_leaders_fill_in_as_games_are_played():
    w = _world()
    while w.day < 12:
        S.advance_one_day(w)
    view = home_view(w)
    assert 1 <= len(view["recent"]) <= 5
    assert view["leaders"] and view["leaders"][0]["ppg"] >= view["leaders"][-1]["ppg"]
    assert "power_rank" in view["standing"]


def test_api_home_works_for_nba_and_college(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from hoopsim.web.app import app
    monkeypatch.chdir(tmp_path)
    for body in ({"league": "nba", "preset": "Quick", "seed": 4},
                 {"league": "college", "economy": "nil", "seed": 7}):
        client = TestClient(app)
        state = client.post("/api/career/new", json=body).json()
        client.post(f"/api/career/team/{state['summary']['teams'][0]['tid']}")
        client.post("/api/sim/week?days=5")
        home = client.get("/api/home").json()
        assert {"inbox", "standing", "recent", "leaders", "news"} <= set(home)
