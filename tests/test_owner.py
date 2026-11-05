"""The owner sets a mandate for the user's team, judges each season against it, and can fire."""
from __future__ import annotations

import pytest

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.world import World
from hoopsim.sim import playoffs as P
from hoopsim.sim import power
from hoopsim.sim import season as S
from hoopsim.systems import owner


def _world(seed=1, pick="best"):
    w = build_world(seed=seed, season_preset="Quick", backstory=False)
    strength = power.projected_strength(w)
    order = sorted(strength, key=strength.get, reverse=True)
    w.user_team_id = {"best": order[0], "mid": order[14], "worst": order[-1]}[pick]
    S.start_season(w)
    owner.begin_season(w)
    return w


def _finish(w, wins, losses, level_bracket=None):
    """Give the user's team a final record and (optionally) a postseason run."""
    team = w.user_team
    team.wins, team.losses = wins, losses
    w.bracket = level_bracket


def test_mandate_follows_preseason_talent():
    best, worst = _world(pick="best"), _world(pick="worst")
    assert best.owner["mandate"]["target"] == owner.FINALS
    assert worst.owner["mandate"]["target"] == owner.MISSED
    assert best.owner["mandate"]["expected_wins"] > worst.owner["mandate"]["expected_wins"]
    assert best.owner["confidence"] == owner.START_CONFIDENCE


def test_beating_expectations_raises_confidence_and_missing_lowers_it():
    up, down = _world(pick="mid"), _world(pick="mid")
    _finish(up, 25, 5)
    _finish(down, 5, 25)
    assert owner.review_season(up)["delta"] > 0
    assert owner.review_season(down)["delta"] < 0


def test_a_rebuild_is_not_marked_down_for_missing_the_playoffs():
    w = _world(pick="worst")
    expected = w.owner["mandate"]["expected_win_pct"]
    wins = round(expected * 30)
    for team in w.team_list():                      # the rest of the league is out of reach
        team.wins, team.losses = 20, 10
    _finish(w, wins, 30 - wins)
    assert abs(owner.review_season(w)["delta"]) <= 3


def test_first_season_is_a_honeymoon_and_the_second_can_end_the_job():
    w = _world(pick="best")
    _finish(w, 2, 28)
    first = owner.review_season(w)
    assert not first["fired"] and first["delta"] >= owner.DELTA_MIN / 2 - 1
    # a refreshed page doesn't review the same season twice
    assert owner.review_season(w) is first
    w.season_year += 1
    w.owner["confidence"] = 30
    w.owner["mandate"] = owner.make_mandate(w)
    _finish(w, 2, 28)
    second = owner.review_season(w)
    assert second["fired"] and w.owner["fired"]
    offers = w.owner["offers"]
    assert len(offers) == owner.OFFER_COUNT == len(set(offers))
    assert w.user_team_id not in offers


def test_taking_a_new_job_moves_the_user_and_frees_the_old_team():
    w = _world(pick="best")
    old = w.user_team
    old.block_list, old.rotation, old.auto_lineup = [old.roster[0]], old.roster[:8], False
    w.owner.update(fired=True, offers=[t.tid for t in w.team_list() if t.tid != old.tid][:3])
    with pytest.raises(ValueError):
        owner.take_job(w, old.tid)
    new_tid = w.owner["offers"][1]
    owner.take_job(w, new_tid)
    assert w.user_team_id == new_tid and not w.owner["fired"]
    assert w.owner["confidence"] == owner.NEW_JOB_CONFIDENCE
    assert w.owner["mandate"]["year"] == w.season_year
    assert old.block_list == [] and old.rotation == [] and old.auto_lineup
    assert w.owner["past_jobs"][0]["tid"] == old.tid


def test_postseason_level_reads_the_real_bracket():
    w = _world(pick="best")
    while not S.regular_season_complete(w):
        S.advance_one_day(w)
    P.start_playoffs(w)
    while not P.playoffs_complete(w):
        P.advance_playoff_slate(w)
    champ = P.champion(w)
    assert owner.postseason_level(w, champ) == owner.CHAMPION
    in_playoffs = {t for s in w.bracket["all_series"] for t in (s["hi"], s["lo"])}
    outside = [t.tid for t in w.team_list() if t.tid not in in_playoffs]
    assert outside and all(owner.postseason_level(w, t) in (owner.MISSED, owner.PLAY_IN)
                           for t in outside)
    finalists = [s for s in w.bracket["all_series"] if s["round"] == "Finals"][0]
    loser = finalists["hi"] if finalists["winner"] == finalists["lo"] else finalists["lo"]
    assert owner.postseason_level(w, loser) == owner.FINALS


def test_owner_saves_with_the_career_and_older_saves_pick_it_up():
    w = _world()
    assert World.from_dict(w.to_dict()).owner == w.owner
    d = w.to_dict()
    d.pop("owner")
    old = World.from_dict(d)
    assert old.owner is None
    assert owner.view(old)["mandate"]["year"] == old.season_year


def test_college_careers_have_no_owner():
    from hoopsim.gen.collegegen import build_college_world
    w = build_college_world(seed=7, economy="nil")
    w.user_team_id = w.team_list()[0].tid
    assert owner.view(w) is None and owner.review_season(w) is None


def test_api_reports_the_owner_and_reviews_the_season(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from hoopsim.web.app import app
    from hoopsim.web.session import SESSIONS
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)
    state = client.post("/api/career/new", json={"league": "nba", "preset": "Quick", "seed": 4}).json()
    summary = client.post(f"/api/career/team/{state['summary']['teams'][0]['tid']}").json()
    assert summary["owner"]["mandate"]["label"] and summary["owner"]["confidence"] == 60
    assert client.post("/api/owner/take-job", json={"tid": 1}).status_code == 400
    world = SESSIONS.get(client.cookies.get("hoopsim_sid"))
    while not S.regular_season_complete(world):
        S.advance_one_day(world)
    client.post("/api/playoffs/start")
    client.post("/api/playoffs/sim-to-end")
    out = client.post("/api/offseason/pre-draft").json()
    review = out["summary"]["owner_review"]
    assert review["year"] == world.season_year and "confidence" in review
    assert client.get("/api/state").json()["summary"]["owner"]["last_review"] == review


def test_a_fired_gm_leaves_the_offseason_to_the_ai(monkeypatch):
    from hoopsim.systems import freeagency, offseason
    w = _world(pick="best")
    tid = w.user_team_id
    w.owner.update(seasons=1, confidence=15)
    _finish(w, 2, 28)
    seen = {}
    real = freeagency.run_retention

    def spy(world):
        seen["user"] = world.user_team_id
        return real(world)
    monkeypatch.setattr(freeagency, "run_retention", spy)
    summary = offseason.pre_draft(w, None)
    assert summary["owner_review"]["fired"]
    assert seen["user"] is None                    # the old team re-signed its own like any AI club
    assert w.user_team_id == tid and w.owner["offers"]    # still ours until a new job is taken
