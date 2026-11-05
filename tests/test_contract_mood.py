"""Players weigh winning, role, loyalty and morale before extending with the user's team."""
from __future__ import annotations

import pytest

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.team import roster_players
from hoopsim.sim import season as S
from hoopsim.systems import cap
from hoopsim.systems import contract_mood as M


def _world(seed=1):
    w = build_world(seed=seed, season_preset="Standard", backstory=False)
    w.user_team_id = w.team_list()[0].tid
    S.start_season(w)
    return w


def _set(w, player, *, wins, losses, mpg, years=1, morale=70, age=None):
    team = w.teams[player.team_id]
    team.wins, team.losses = wins, losses
    player.season.gp = 40
    player.season.secs = int(mpg * 60 * 40)
    player.contract.years_with_team = years
    player.morale = morale
    if age is not None:
        player.age = age
    return player


def _star(w):
    return max(roster_players(w.user_team, w.players), key=lambda p: p.overall)


def test_winning_role_and_loyalty_make_a_player_eager_and_losing_on_the_bench_drives_him_off():
    w = _world()
    p = _set(w, _star(w), wins=30, losses=10, mpg=35, years=5, morale=80)
    assert M.assess(w, p)["level"] == M.EAGER
    p = _set(w, p, wins=8, losses=32, mpg=12, years=0, morale=50, age=30)
    mood = M.assess(w, p)
    assert mood["level"] == M.TESTING_FA
    assert any("winner" in r for r in mood["reasons"]) and any("role" in r for r in mood["reasons"])


def test_stance_sets_the_asking_price():
    w = _world()
    p = _star(w)
    market = min(cap.market_salary(p), cap.max_salary(p.experience, w.salary_cap))
    _set(w, p, wins=30, losses=10, mpg=35, years=5, morale=80)
    eager = cap.extension_offer(w, p, for_user=True)[0]
    _set(w, p, wins=16, losses=24, mpg=34, years=0, morale=65)
    assert M.assess(w, p)["level"] == M.WANTS_MORE
    sour = cap.extension_offer(w, p, for_user=True)[0]
    assert eager < market or eager == cap.max_salary(p.experience, w.salary_cap)
    assert sour >= market and sour > eager
    assert cap.extension_offer(w, p)[0] == market            # AI re-signings pay plain market


def test_a_player_testing_free_agency_refuses_the_user_but_not_the_ai():
    w = _world()
    p = _set(w, _star(w), wins=8, losses=32, mpg=12, years=0, morale=50, age=30)
    salary, years = cap.extension_offer(w, p, for_user=True)
    ok, why = cap.extend_contract(w, w.user_team, p.pid, salary, years, for_user=True)
    assert not ok and "free agency" in why
    assert cap.extend_contract(w, w.user_team, p.pid, salary, years)[0]


def test_the_user_must_meet_the_ask():
    w = _world()
    p = _set(w, _star(w), wins=24, losses=16, mpg=33, years=2)
    ask, years = cap.extension_offer(w, p, for_user=True)
    ok, why = cap.extend_contract(w, w.user_team, p.pid, ask - 1_000_000, years, for_user=True)
    assert not ok and "wants about" in why
    assert cap.extend_contract(w, w.user_team, p.pid, ask, years, for_user=True)[0]


def test_moods_spread_across_the_league_mid_season():
    levels = []
    for seed in (1, 2):
        w = _world(seed)
        while w.day < 30:
            S.advance_one_day(w)
        levels += [M.assess(w, p)["level"] for t in w.team_list()
                   for p in roster_players(t, w.players)]
    share = {lvl: levels.count(lvl) / len(levels) for lvl in M.LABELS}
    # most players will talk, but refusing is a real outcome, not a rare edge case
    assert share[M.EAGER] + share[M.OPEN] > 0.5
    assert 0.05 < share[M.TESTING_FA] < 0.30


def test_api_previews_the_stance_and_rejects_a_lowball(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from hoopsim.web.app import app
    from hoopsim.web.session import SESSIONS
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)
    state = client.post("/api/career/new", json={"league": "nba", "preset": "Quick", "seed": 4}).json()
    client.post(f"/api/career/team/{state['summary']['teams'][0]['tid']}")
    w = SESSIONS.get(client.cookies.get("hoopsim_sid"))
    p = _set(w, _star(w), wins=20, losses=10, mpg=33, years=3)
    pre = client.get(f"/api/extend/preview?pid={p.pid}").json()
    assert pre["willing"] and pre["label"] and pre["salary"] > 0
    lowball = client.post("/api/extend", json={"pid": p.pid, "salary": 1_000_000}).json()
    assert lowball["extended"] is False
    assert client.post("/api/extend", json={"pid": p.pid}).json()["extended"] is True
