"""Smoke tests for the web layer: serializers match the engine, and the API drives a game.

Skipped automatically if the optional ``web`` extra (fastapi/httpx) is not installed.
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from hoopsim.gen.leaguegen import build_world  # noqa: E402
from hoopsim.models.league import conference_standings  # noqa: E402
from hoopsim.models.team import roster_players  # noqa: E402
from hoopsim.web import serializers as ser  # noqa: E402
from hoopsim.web.app import _LIVE, app  # noqa: E402
from hoopsim.web.session import SESSIONS  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_saves(tmp_path, monkeypatch):
    """Saves land under the cwd, so keep every test's autosaves out of the real ``saves/``."""
    monkeypatch.chdir(tmp_path)


def _career(client, seed=3, pick_best=False):
    """Start a Quick NBA career and return its world."""
    state = client.post("/api/career/new",
                        json={"league": "nba", "preset": "Quick", "seed": seed}).json()
    world = SESSIONS.get(client.cookies.get("hoopsim_sid"))
    tid = state["summary"]["teams"][0]["tid"]
    if pick_best:
        tid = max(world.team_list(), key=lambda t: sum(
            sorted((world.players[p].overall for p in t.roster), reverse=True)[:8])).tid
    client.post(f"/api/career/team/{tid}")
    return world


def _open_live_game(client, route="/api/sim/game?watch=true"):
    """Watch games until one reaches a crunch-time decision, and return that response."""
    for _ in range(60):
        out = client.post(route).json()
        if out.get("status") == "decision":
            return out
    pytest.fail("no watched game ever reached a crunch-time decision")


def _user_games_played(world):
    return sum(1 for g in world.schedule if g.played and g.involves(world.user_team_id))


def test_export_then_import_restores_the_career_in_a_fresh_session():
    original = TestClient(app)
    _career(original)
    original.post("/api/sim/week?days=3")
    exported = original.get("/api/save/export")
    assert exported.status_code == 200
    assert 'attachment; filename="' in exported.headers["content-disposition"]

    fresh = TestClient(app)
    assert fresh.post("/api/save/import", content=exported.content).status_code == 200
    assert fresh.get("/api/save/export").content == exported.content
    # the imported autosave is on this session's disk too, so it survives a process restart
    assert "autosave" in fresh.get("/api/saves").json()["saves"]


def test_import_rejects_a_bad_file_and_keeps_the_current_career():
    client = TestClient(app)
    _career(client)
    before = client.get("/api/save/export").content
    for bad in (b"not json", b"[]", b"{}", b"\xff\xfe"):
        assert client.post("/api/save/import", content=bad).status_code == 400
    assert client.get("/api/save/export").content == before


def test_export_waits_for_an_open_live_game():
    client = TestClient(app)
    _career(client)
    _open_live_game(client)
    assert client.get("/api/save/export").status_code == 409


def test_simming_past_an_open_live_game_counts_it_exactly_once():
    client = TestClient(app)
    world = _career(client)
    _open_live_game(client)
    played = _user_games_played(world)
    assert client.post("/api/sim/week?days=1").status_code == 200
    team = world.user_team
    # the open game finished, then one more day was simmed — every win or loss is a real game
    assert _user_games_played(world) >= played + 1
    assert team.wins + team.losses == _user_games_played(world)
    assert client.cookies.get("hoopsim_sid") not in _LIVE
    # the tab still showing that game can't apply it a second time
    assert client.post("/api/sim/coach", json={}).status_code == 409
    assert team.wins + team.losses == _user_games_played(world)


def test_quick_sim_finishes_the_open_game_rather_than_skipping_to_the_next():
    client = TestClient(app)
    world = _career(client)
    _open_live_game(client)
    played = _user_games_played(world)
    out = client.post("/api/sim/game").json()
    assert out["status"] == "final" and "result" in out
    assert _user_games_played(world) == played + 1


def test_watch_reopens_the_open_game_with_its_decision_and_log():
    client = TestClient(app)
    world = _career(client)
    # Some games end on the first order, and an empty log would prove nothing below.
    for _ in range(30):
        first = _open_live_game(client)
        latest = client.post("/api/sim/coach", json={}).json()
        log = first["events"] + latest.get("events", [])
        if latest["status"] == "decision" and log:
            break
    else:
        pytest.fail("no live game ran to a second decision with a log")
    played = _user_games_played(world)
    again = client.post("/api/sim/game?watch=true").json()
    assert again["status"] == "decision"
    assert again["decision"] == latest["decision"]
    assert again["events"] == log
    assert _user_games_played(world) == played


def test_reopening_a_playoff_game_does_not_replay_the_other_series():
    client = TestClient(app)
    world = _career(client, pick_best=True)
    while not client.post("/api/sim/week?days=10").json()["season_complete"]:
        pass
    client.post("/api/playoffs/start")
    first = _open_live_game(client, "/api/playoffs/advance?watch=true")
    bracket = json.dumps(world.bracket, sort_keys=True)
    again = client.post("/api/playoffs/advance?watch=true").json()
    assert again["decision"] == first["decision"]
    assert json.dumps(world.bracket, sort_keys=True) == bracket


def test_loading_a_save_discards_the_open_live_game():
    client = TestClient(app)
    _career(client)
    client.post("/api/save", json={"slot": "before"})
    _open_live_game(client)
    assert client.post("/api/load", json={"slot": "before"}).status_code == 200
    assert client.cookies.get("hoopsim_sid") not in _LIVE
    assert client.post("/api/sim/coach", json={}).status_code == 409


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
    from hoopsim.systems.trades import (TRADE_BLOCK_MAX_YEARS, TRADE_BLOCK_VET_AGE,
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


def test_api_set_and_clear_role():
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "nba", "preset": "Quick", "seed": 5}).json()
    tid = state["summary"]["teams"][0]["tid"]
    client.post(f"/api/career/team/{tid}")
    roster = client.get(f"/api/teams/{tid}/roster").json()
    assert "closer" in roster["role_tags"]
    pid = roster["players"][0]["pid"]
    view = client.post("/api/role", json={"role": "closer", "pid": pid}).json()
    assert view["roles"]["closer"] == pid
    cleared = client.post("/api/role", json={"role": "closer", "pid": None}).json()
    assert "closer" not in cleared["roles"]
    bad = client.post("/api/role", json={"role": "bogus", "pid": pid})
    assert bad.status_code == 400


def test_api_waive_and_extend():
    from hoopsim.config import ROSTER_MIN
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


def test_api_rotation_pins_minutes():
    """Pinning a deep-bench player via /api/rotation gives him minutes and zeroes the rest."""
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "nba", "preset": "Quick", "seed": 5}).json()
    tid = state["summary"]["teams"][0]["tid"]
    client.post(f"/api/career/team/{tid}")

    roster = client.get(f"/api/teams/{tid}/roster").json()
    starters = set(roster["starters"])
    assert roster["manual_rotation"] is False
    bench = sorted((p for p in roster["players"] if p["pid"] not in starters),
                   key=lambda p: p["overall"])
    rookie = bench[0]                                  # lowest-overall reserve, likely 0 minutes

    view = client.post("/api/rotation", json={"rotation": [rookie["pid"]]}).json()
    assert view["manual_rotation"] is True
    assert rookie["pid"] in view["rotation"]
    mins = {p["pid"]: p["minutes"] for p in view["players"]}
    assert mins[rookie["pid"]] > 0
    # every non-starter who wasn't pinned is parked at the end of the bench
    for p in view["players"]:
        if p["pid"] not in starters and p["pid"] != rookie["pid"]:
            assert p["minutes"] == 0

    cleared = client.post("/api/rotation", json={"rotation": None}).json()
    assert cleared["manual_rotation"] is False


def test_offseason_pre_draft_is_idempotent():
    """Re-entering the offseason wizard must not run the offseason twice (the reported bug)."""
    from hoopsim.models.league import Phase
    from hoopsim.web.session import SESSIONS
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "nba", "preset": "Quick", "seed": 5}).json()
    tid = state["summary"]["teams"][0]["tid"]
    client.post(f"/api/career/team/{tid}")
    sid = client.cookies.get("hoopsim_sid")
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
    from hoopsim.systems import cap, trades
    from hoopsim.web.session import SESSIONS
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "nba", "preset": "Quick", "seed": 8}).json()
    tid = state["summary"]["teams"][0]["tid"]
    client.post(f"/api/career/team/{tid}")
    world = SESSIONS.require(client.cookies.get("hoopsim_sid"))

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
    from hoopsim.models.league import Phase
    from hoopsim.sim import playoffs as P
    from hoopsim.systems import offseason
    from hoopsim.web.session import SESSIONS
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "nba", "preset": "Quick", "seed": 2}).json()
    tid = state["summary"]["teams"][0]["tid"]
    client.post(f"/api/career/team/{tid}")
    world = SESSIONS.require(client.cookies.get("hoopsim_sid"))

    # play the whole season + playoffs, then archive it
    from hoopsim.sim import season as S
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

    # Hall of Fame + all-time leaderboards endpoints respond and are well-formed.
    hof = client.get("/api/hall-of-fame").json()
    assert "members" in hof and isinstance(hof["members"], list)
    board = client.get("/api/leaderboards?category=pts").json()
    assert board["category"] == "pts" and "pts" in board["categories"]
    if board["rows"]:
        pts = [r["totals"]["pts"] for r in board["rows"]]
        assert pts == sorted(pts, reverse=True)       # ranked, highest first


def test_api_college_postseason_crowns_champion():
    """College worlds drive conference tournaments then a national tournament on the web.

    Regression: the web playoff endpoints used to route everything through the NBA bracket,
    which crashed with IndexError on a college world (8 conferences, no 6/4 play-in).
    """
    from hoopsim.sim import season as S
    from hoopsim.web.session import SESSIONS
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "college", "economy": "nil", "seed": 7}).json()
    assert state["summary"]["mode"] == "college"
    tid = state["summary"]["teams"][0]["tid"]
    client.post(f"/api/career/team/{tid}")
    world = SESSIONS.require(client.cookies.get("hoopsim_sid"))

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
    from hoopsim.sim import season as S
    from hoopsim.web.session import SESSIONS
    client = TestClient(app)
    state = client.post("/api/career/new",
                        json={"league": "college", "economy": "nil", "seed": 11}).json()
    tid = state["summary"]["teams"][0]["tid"]
    client.post(f"/api/career/team/{tid}")
    world = SESSIONS.require(client.cookies.get("hoopsim_sid"))
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
    assert board["wave"]["active"] and board["wave"]["wave"] == 1   # opens at the top tier

    # Signing Day resolves in waves (top tier first); work each wave until the board clears.
    total = 0
    while True:
        board = client.get("/api/recruiting").json()
        top = board["recruits"][0]["pid"] if board["recruits"] else None
        offers = {str(top): 1_500_000} if top is not None else {}
        sign = client.post("/api/recruiting/sign", json={"offers": offers}).json()
        total += sign["total"]
        if sign["done"]:
            break
    assert total > 0                                        # recruiting resolved league-wide
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
