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
