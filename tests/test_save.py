"""Save/load round-trip and determinism tests."""
from __future__ import annotations

from hoopr.gen.leaguegen import build_world
from hoopr.save import store
from hoopr.save.serialize import world_from_json, world_to_json
from hoopr.sim import playoffs as P
from hoopr.sim import season as S
from hoopr.sim.engine import simulate_game


def _rich_world(seed=1):
    """A world exercising most serialized fields: stats, schedule, and a live bracket."""
    w = build_world(seed=seed)
    w.user_team_id = 3
    w.season_games = 12
    S.start_season(w)
    while not S.regular_season_complete(w):
        S.advance_one_day(w)
    P.start_playoffs(w)
    P.advance_playoff_slate(w)
    return w


def test_round_trip_is_byte_identical():
    w = _rich_world(seed=2)
    once = world_to_json(w)
    twice = world_to_json(world_from_json(once))
    assert once == twice


def test_round_trip_preserves_state():
    w = _rich_world(seed=5)
    w2 = world_from_json(world_to_json(w))
    assert w2.season_year == w.season_year
    assert w2.phase == w.phase
    assert w2.user_team_id == w.user_team_id
    assert len(w2.teams) == len(w.teams)
    assert len(w2.players) == len(w.players)
    assert len(w2.schedule) == len(w.schedule)
    # standings line up
    for tid, team in w.teams.items():
        assert w2.teams[tid].wins == team.wins
        assert w2.teams[tid].losses == team.losses
    # a player's accumulated stats survive
    pid = next(iter(w.players))
    assert w2.players[pid].season.to_dict() == w.players[pid].season.to_dict()
    assert w2.bracket == w.bracket


def test_round_trip_preserves_traded_draft_picks():
    from hoopr.systems.trades import TradeOffer, execute_trade
    w = build_world(seed=7)
    a, b = w.teams[0], w.teams[1]
    ka = w.find_pick(w.season_year, 1, a.tid).key
    kb = w.find_pick(w.season_year, 1, b.tid).key
    execute_trade(w, TradeOffer(a.tid, b.tid, [], [], [ka], [kb]))
    w2 = world_from_json(world_to_json(w))
    assert len(w2.draft_picks) == len(w.draft_picks)
    assert w2.find_pick(*ka).owner_tid == b.tid
    assert w2.find_pick(*kb).owner_tid == a.tid


def test_rng_state_reproduces_simulation():
    w = build_world(seed=9)
    w.user_team_id = 0
    S.start_season(w)
    # snapshot the world (and thus the RNG state) before simulating
    saved = world_to_json(w)
    reloaded = world_from_json(saved)

    a, b = w.teams[0], w.teams[1]
    r1 = simulate_game(w, w.teams[0], w.teams[1])
    r2 = simulate_game(reloaded, reloaded.teams[0], reloaded.teams[1])
    assert (r1.home_score, r1.away_score) == (r2.home_score, r2.away_score)
    assert r1.line_score == r2.line_score


def test_save_slots_on_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    w = build_world(seed=4)
    w.user_team_id = 1
    store.save_game(w, "My Save 1")
    assert "My_Save_1" in store.list_saves()
    assert store.exists("My Save 1")
    loaded = store.load_game("My Save 1")
    assert loaded.user_team_id == 1
    store.autosave(w)
    assert store.exists("autosave")
    store.delete_save("My Save 1")
    assert not store.exists("My Save 1")
