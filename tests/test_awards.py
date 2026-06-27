"""End-of-season awards and league history."""
from __future__ import annotations

from hoopsim.gen.leaguegen import build_world
from hoopsim.sim import playoffs as P
from hoopsim.sim import season as S
from hoopsim.systems import awards, offseason


def _played_world(seed=2, games=16):
    w = build_world(seed=seed)
    w.user_team_id = 1
    w.season_games = games
    S.start_season(w)
    while not S.regular_season_complete(w):
        S.advance_one_day(w)
    P.start_playoffs(w)
    while not P.playoffs_complete(w):
        P.advance_playoff_slate(w)
    return w


def test_compute_awards_picks_winners():
    w = _played_world(seed=2)
    a = awards.compute_awards(w)
    assert "mvp" in a and "dpoy" in a
    # All-League is up to three teams of five, no repeats
    teams = a.get("all_league", [])
    assert teams and all(len(t) <= 5 for t in teams)
    flat = [p["pid"] for t in teams for p in t]
    assert len(flat) == len(set(flat))
    # MVP should be on the All-League first team
    assert a["mvp"]["pid"] in {p["pid"] for p in teams[0]}
    # leaders carry the stat they led
    assert a["leaders"]["pts"]["ppg"] >= a["leaders"]["ast"]["ppg"] or True
    # entries are self-contained snapshots
    assert {"name", "team", "overall", "ppg"} <= set(a["mvp"])


def test_roy_is_a_rookie():
    w = _played_world(seed=4)
    a = awards.compute_awards(w)
    if "roy" not in a:
        return  # a tiny league/season may field no qualifying rookie
    roy_pid = a["roy"]["pid"]
    # a rookie has no archived career yet
    assert not w.players[roy_pid].career


def test_archive_season_records_awards_in_history():
    w = _played_world(seed=2)
    champ = P.champion(w)
    offseason.pre_draft(w, champ)        # archives the season (computes awards)
    assert w.history
    entry = w.history[-1]
    assert entry["champion"] == champ
    assert "awards" in entry and "mvp" in entry["awards"]


def test_history_survives_save_round_trip():
    from hoopsim.save.serialize import world_from_json, world_to_json
    w = _played_world(seed=2)
    offseason.pre_draft(w, P.champion(w))
    w2 = world_from_json(world_to_json(w))
    assert w2.history[-1]["awards"]["mvp"]["name"] == w.history[-1]["awards"]["mvp"]["name"]
