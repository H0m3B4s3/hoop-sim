"""Smoke tests for the web layer: serializers match the engine, and the API drives a game.

Skipped automatically if the optional ``web`` extra (fastapi/httpx) is not installed.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from hoopr.gen.leaguegen import build_world  # noqa: E402
from hoopr.models.league import conference_standings  # noqa: E402
from hoopr.models.team import roster_players  # noqa: E402
from hoopr.web import serializers as ser  # noqa: E402
from hoopr.web.app import app  # noqa: E402


def test_roster_view_numbers_match_models():
    world = build_world(seed=99, season_preset="Quick")
    team = world.team_list()[0]
    view = ser.roster_view(world, team)
    assert len(view["players"]) == len(team.roster)
    # rows are ordered by overall, descending — same as the terminal roster table
    overalls = [r["overall"] for r in view["players"]]
    assert overalls == sorted(overalls, reverse=True)
    best = max(roster_players(team, world.players), key=lambda p: p.overall)
    assert view["players"][0]["pid"] == best.pid
    assert view["players"][0]["overall"] == best.overall


def test_standings_view_order_matches_engine():
    world = build_world(seed=7, season_preset="Quick")
    view = ser.standings_view(world)
    for conf in view["conferences"]:
        engine_order = [t.tid for t in conference_standings(world.team_list(), conf["conference"])]
        assert [row["tid"] for row in conf["teams"]] == engine_order


def test_color_hex_resolves_named_colors():
    assert ser.color_hex("navy_blue").startswith("#")
    assert ser.color_hex("not-a-real-color").startswith("#")  # falls back, never raises


def test_scouting_view_covers_league_and_flags_block():
    world = build_world(seed=7, season_preset="Quick")
    world.user_team_id = world.team_list()[0].tid
    view = ser.scouting_view(world)
    rostered = sum(len(t.roster) for t in world.team_list())
    assert len(view["players"]) == rostered + len(world.free_agents)
    assert "composites" in view["players"][0]
    # the user's own players are never flagged as shopped to themselves
    user_rows = [r for r in view["players"] if r["team_id"] == world.user_team_id]
    assert user_rows and not any(r["on_block"] for r in user_rows)


def test_trade_block_is_aging_vets_on_expiring_deals():
    from hoopr.systems.trades import (TRADE_BLOCK_MAX_YEARS, TRADE_BLOCK_VET_AGE,
                                      team_trade_block)
    world = build_world(seed=7, season_preset="Quick")
    for team in world.team_list():
        for pid in team_trade_block(world, team):
            p = world.players[pid]
            assert p.age >= TRADE_BLOCK_VET_AGE
            assert 0 < p.contract.years_remaining <= TRADE_BLOCK_MAX_YEARS


def test_api_scouting_and_trade_block_endpoints():
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "nba", "preset": "Quick", "seed": 3}).json()
    tid = state["summary"]["teams"][0]["tid"]
    client.post(f"/api/career/team/{tid}")
    scout = client.get("/api/scouting").json()
    assert scout["players"] and "composite_order" in scout
    other = next(t["tid"] for t in state["summary"]["teams"] if t["tid"] != tid)
    blk = client.get(f"/api/teams/{other}/trade-block").json()
    assert blk["tid"] == other and isinstance(blk["pids"], list)


def test_api_solicit_and_accept_offer():
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "nba", "preset": "Quick", "seed": 8}).json()
    tid = state["summary"]["teams"][0]["tid"]
    client.post(f"/api/career/team/{tid}")
    roster = client.get(f"/api/teams/{tid}/roster").json()
    target = max(roster["players"], key=lambda p: p["overall"])["pid"]
    offers = client.post("/api/trade/solicit", json={"pids": [target]}).json()["offers"]
    assert offers, "expected offers for a top player"
    top = offers[0]
    assert top["user_sends"] == [target] and top["pieces"]
    accepted = client.post("/api/trade/accept", json={
        "partner_tid": top["partner_tid"],
        "user_sends": top["user_sends"],
        "partner_sends": top["partner_sends"],
    }).json()
    assert accepted["executed"] is True
    after = client.get(f"/api/teams/{tid}/roster").json()
    pids_after = {p["pid"] for p in after["players"]}
    assert target not in pids_after
    assert all(pid in pids_after for pid in top["partner_sends"])


def test_api_trade_draft_picks():
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "nba", "preset": "Quick", "seed": 8}).json()
    tid = state["summary"]["teams"][0]["tid"]
    other = next(t["tid"] for t in state["summary"]["teams"] if t["tid"] != tid)
    client.post(f"/api/career/team/{tid}")

    mine = client.get(f"/api/teams/{tid}/picks").json()["picks"]
    theirs = client.get(f"/api/teams/{other}/picks").json()["picks"]
    assert mine and theirs and "label" in mine[0] and "value" in mine[0]

    my_key = mine[0]["key"]
    their_key = theirs[0]["key"]
    body = {"partner_tid": other, "user_sends": [], "partner_sends": [],
            "user_picks": [my_key], "partner_picks": [their_key]}
    val = client.post("/api/trade/validate", json=body).json()
    assert val["legal"] is True
    ex = client.post("/api/trade/accept", json=body).json()
    assert ex["executed"] is True

    after_mine = {tuple(p["key"]) for p in client.get(f"/api/teams/{tid}/picks").json()["picks"]}
    assert tuple(their_key) in after_mine and tuple(my_key) not in after_mine


def test_api_depth_chart_groups_by_position():
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "nba", "preset": "Quick", "seed": 5}).json()
    tid = state["summary"]["teams"][0]["tid"]
    client.post(f"/api/career/team/{tid}")
    dc = client.get(f"/api/teams/{tid}/depth-chart").json()
    positions = [g["position"] for g in dc["positions"]]
    assert positions == ["PG", "SG", "SF", "PF", "C"]
    # every rostered player lands in exactly one position group
    total = sum(g["count"] for g in dc["positions"])
    roster = client.get(f"/api/teams/{tid}/roster").json()["players"]
    assert total == len(roster)
    # starters are flagged and within their position group sort to the front
    for g in dc["positions"]:
        if g["players"]:
            assert g["players"] == sorted(
                g["players"], key=lambda p: (p["is_starter"], p["overall"]), reverse=True)
    assert any(p["is_starter"] for g in dc["positions"] for p in g["players"])


def test_api_waive_and_extend():
    from hoopr.config import ROSTER_MIN
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "nba", "preset": "Quick", "seed": 5}).json()
    tid = state["summary"]["teams"][0]["tid"]
    client.post(f"/api/career/team/{tid}")

    roster = client.get(f"/api/teams/{tid}/roster").json()["players"]
    assert len(roster) > ROSTER_MIN
    # extend a player — response carries the refreshed summary
    target = min(roster, key=lambda p: p["years_remaining"])["pid"]
    ext = client.post("/api/extend", json={"pid": target}).json()
    assert "extended" in ext and "summary" in ext

    # waive down toward the floor, asserting each legal waive succeeds
    waived = 0
    while True:
        cur = client.get(f"/api/teams/{tid}/roster").json()["players"]
        if len(cur) <= ROSTER_MIN:
            break
        assert client.post("/api/waive", json={"pid": cur[0]["pid"]}).json()["waived"] is True
        waived += 1
    assert waived >= 1
    # at the floor the next waive is refused, as is waiving a non-rostered player
    floor_roster = client.get(f"/api/teams/{tid}/roster").json()["players"]
    assert client.post("/api/waive", json={"pid": floor_roster[0]["pid"]}).status_code == 400
    assert client.post("/api/waive", json={"pid": 999999}).status_code == 400


def test_offseason_pre_draft_is_idempotent():
    """Re-entering the offseason wizard must not run the offseason twice (the reported bug)."""
    from hoopr.models.league import Phase
    from hoopr.web.session import SESSIONS
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "nba", "preset": "Quick", "seed": 5}).json()
    tid = state["summary"]["teams"][0]["tid"]
    client.post(f"/api/career/team/{tid}")
    sid = client.cookies.get("hoopr_sid")
    world = SESSIONS.require(sid)

    # Simulate "playoffs just ended": offseason available, not yet begun.
    world.phase = Phase.DRAFT
    world.draft_class = None
    assert client.get("/api/state").json()["summary"]["offseason_stage"] == "pre_draft"

    # First begin: ages everyone +1 and sets up the draft.
    ages0 = {pid: p.age for pid, p in world.players.items()}
    r1 = client.post("/api/offseason/pre-draft").json()
    assert not r1.get("resumed")
    assert client.get("/api/state").json()["summary"]["offseason_stage"] == "draft"
    aged = {pid: p.age for pid, p in world.players.items() if pid in ages0}
    assert any(aged[pid] == ages0[pid] + 1 for pid in aged)

    # Second begin (e.g. user left the tab and came back): a no-op, no second aging.
    snapshot = {pid: p.age for pid, p in world.players.items()}
    r2 = client.post("/api/offseason/pre-draft").json()
    assert r2.get("resumed") is True
    assert {pid: p.age for pid, p in world.players.items()} == snapshot


def test_api_block_and_offers_inbox():
    from hoopr.systems import cap, trades
    from hoopr.web.session import SESSIONS
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "nba", "preset": "Quick", "seed": 8}).json()
    tid = state["summary"]["teams"][0]["tid"]
    client.post(f"/api/career/team/{tid}")
    world = SESSIONS.require(client.cookies.get("hoopr_sid"))

    # put a quality vet on the block via the endpoint
    pid = max(world.teams[tid].roster, key=lambda p: cap.trade_value(world.players[p]))
    r = client.post("/api/block", json={"pid": pid, "on": True}).json()
    assert r["on_block"] is True
    # roster rows reflect the block flag
    roster = client.get(f"/api/teams/{tid}/roster").json()["players"]
    assert next(p for p in roster if p["pid"] == pid)["on_block"] is True

    # generate offers (advance the offer clock directly to avoid simming a full season)
    for _ in range(60):
        trades.refresh_offers(world)
        if world.trade_offers:
            break
        world.day += 1
    assert world.trade_offers

    inbox = client.get("/api/offers").json()["offers"]
    assert inbox and pid in inbox[0]["user_sends"]
    assert client.get("/api/state").json()["summary"]["open_offers"] == len(inbox)

    # accept the first offer through the endpoint
    res = client.post("/api/offers/accept", json={"id": inbox[0]["id"]}).json()
    assert res["executed"] is True
    after = {p["pid"] for p in client.get(f"/api/teams/{tid}/roster").json()["players"]}
    assert pid not in after


def test_api_history_after_a_season():
    from hoopr.models.league import Phase
    from hoopr.sim import playoffs as P
    from hoopr.systems import offseason
    from hoopr.web.session import SESSIONS
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "nba", "preset": "Quick", "seed": 2}).json()
    tid = state["summary"]["teams"][0]["tid"]
    client.post(f"/api/career/team/{tid}")
    world = SESSIONS.require(client.cookies.get("hoopr_sid"))

    # play the whole season + playoffs, then archive it
    from hoopr.sim import season as S
    while not S.regular_season_complete(world):
        S.advance_one_day(world)
    P.start_playoffs(world)
    while not P.playoffs_complete(world):
        P.advance_playoff_slate(world)
    offseason.pre_draft(world, P.champion(world))

    hist = client.get("/api/history").json()["history"]
    assert hist and "champion_abbrev" in hist[0]
    mvp = hist[0]["awards"]["mvp"]
    assert mvp["name"] and "team_color" in mvp


def test_api_college_postseason_crowns_champion():
    """College worlds drive conference tournaments then a national tournament on the web.

    Regression: the web playoff endpoints used to route everything through the NBA bracket,
    which crashed with IndexError on a college world (8 conferences, no 6/4 play-in).
    """
    from hoopr.sim import season as S
    from hoopr.web.session import SESSIONS
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "college", "economy": "nil", "seed": 7}).json()
    assert state["summary"]["mode"] == "college"
    tid = state["summary"]["teams"][0]["tid"]
    client.post(f"/api/career/team/{tid}")
    world = SESSIONS.require(client.cookies.get("hoopr_sid"))

    # Fast-forward the regular season directly, then drive the postseason through the API.
    while not S.regular_season_complete(world):
        S.advance_one_day(world)

    start = client.post("/api/playoffs/start").json()
    assert start["bracket"]["type"] == "college"
    assert start["bracket"]["stage"] == "conf"
    assert "all_series" not in start["bracket"]      # not the NBA series bracket

    # Advance slates until a national champion is crowned.
    for _ in range(60):
        if client.get("/api/playoffs").json()["complete"]:
            break
        client.post("/api/playoffs/advance", params={"watch": False})
    else:
        raise AssertionError("college postseason did not complete")

    final = client.get("/api/playoffs").json()
    assert final["complete"] is True
    champ = final["champion"]
    assert champ is not None and world.find_team(champ) is not None
    assert final["bracket"]["national"]["champion"] == champ


def test_api_college_offseason_advances_to_next_season():
    """College offseason on the web: NBA draft pipeline → recruiting → next season."""
    from hoopr.sim import season as S
    from hoopr.web.session import SESSIONS
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "college", "economy": "nil", "seed": 11}).json()
    tid = state["summary"]["teams"][0]["tid"]
    client.post(f"/api/career/team/{tid}")
    world = SESSIONS.require(client.cookies.get("hoopr_sid"))
    year0 = world.season_year

    while not S.regular_season_complete(world):
        S.advance_one_day(world)
    client.post("/api/playoffs/start")
    for _ in range(60):
        if client.get("/api/playoffs").json()["complete"]:
            break
        client.post("/api/playoffs/advance", params={"watch": False})

    assert client.get("/api/state").json()["summary"]["offseason_stage"] == "pre_recruiting"

    begin = client.post("/api/offseason/college/begin").json()
    assert begin["resumed"] is False
    assert "declared" in begin["summary"] and "drafted" in begin["summary"]
    assert client.get("/api/state").json()["summary"]["offseason_stage"] == "recruiting"

    # Re-entering (e.g. a tab refresh) must not re-run eligibility/aging.
    assert client.post("/api/offseason/college/begin").json()["resumed"] is True

    board = client.get("/api/recruiting").json()
    assert board["recruits"] and "nil_available" in board

    top = board["recruits"][0]["pid"]
    sign = client.post("/api/recruiting/sign", json={"offers": {str(top): 1_500_000}}).json()
    assert "signed" in sign and sign["total"] > 0           # recruiting resolved league-wide
    assert world.season_year == year0 + 1                   # rolled into the next season
    assert sign["summary"]["phase"] == "regular_season"
    assert client.get("/api/state").json()["summary"]["offseason_stage"] is None


def test_api_drives_a_short_game_loop():
    client = TestClient(app)
    assert client.get("/api/state").json()["active"] is False

    r = client.post("/api/career/new", json={"league": "nba", "preset": "Quick", "seed": 3})
    tid = r.json()["summary"]["teams"][0]["tid"]
    assert r.json()["needs_team"] is True

    s = client.post(f"/api/career/team/{tid}").json()
    assert s["phase"] == "regular_season"
    assert s["user_team"]["tid"] == tid

    roster = client.get(f"/api/teams/{tid}/roster").json()
    assert roster["players"]

    week = client.post("/api/sim/week", params={"days": 2}).json()
    assert week["summary"]["day"] >= 2

    standings = client.get("/api/standings").json()
    assert sum(len(c["teams"]) for c in standings["conferences"]) == len(s["teams"])
