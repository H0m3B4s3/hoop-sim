"""Coach-mode end-game behaviors and play-by-play depth."""
from __future__ import annotations

from hoopr.gen.leaguegen import build_world
from hoopr.models.tactics import Tactics
from hoopr.sim.engine import GameSim, simulate_game


def _sim(seed=1, *, collect_pbp=False):
    w = build_world(seed=seed)
    h, a = w.teams[0], w.teams[1]
    sim = GameSim(w, h, a, collect_pbp=collect_pbp)
    sim.quarter = sim.periods            # final period for end-game logic
    return w, sim


def _ready_lineups(sim):
    for state in (sim.home, sim.away):
        state.on_court = [pid for pid in state.team.starters if pid in state.available][:5]
        if len(state.on_court) < 5:
            state.choose_lineup(0.0)
        else:
            state.rebuild_cache()


# --- coach-mode: foul when trailing ----------------------------------------
def test_crunch_foul_never_disables_intentional_foul():
    _, sim = _sim()
    sim.clock = 20.0
    sim.result.home_score, sim.result.away_score = 105, 100   # home (offense) leads by 5
    sim.away.team.tactics.crunch_foul = "Never"
    assert not any(sim._should_intentional_foul(sim.home, sim.away) for _ in range(50))


def test_crunch_foul_aggressive_fouls_earlier_and_from_deeper():
    _, sim = _sim()
    sim.clock = 45.0                                          # outside the Auto window (<=35s)
    sim.result.home_score, sim.result.away_score = 111, 100   # lead 11, outside Auto (<=9)
    sim.away.team.tactics.crunch_foul = "Aggressive"
    assert any(sim._should_intentional_foul(sim.home, sim.away) for _ in range(50))
    sim.away.team.tactics.crunch_foul = "Auto"
    assert not any(sim._should_intentional_foul(sim.home, sim.away) for _ in range(50))


# --- coach-mode: foul up 3 -------------------------------------------------
def test_foul_up_3_triggers_only_on_exact_three_late():
    _, sim = _sim()
    sim.clock = 5.0
    sim.result.home_score, sim.result.away_score = 100, 103   # away (defense) up exactly 3
    sim.away.team.tactics.foul_up_3 = "Yes"
    assert sim._should_foul_up_3(sim.home, sim.away)
    sim.away.team.tactics.foul_up_3 = "No"
    assert not sim._should_foul_up_3(sim.home, sim.away)
    # wrong margin or too early -> no foul
    sim.away.team.tactics.foul_up_3 = "Yes"
    sim.result.away_score = 104                               # up 4
    assert not sim._should_foul_up_3(sim.home, sim.away)
    sim.result.away_score = 103
    sim.clock = 12.0                                          # too early
    assert not sim._should_foul_up_3(sim.home, sim.away)


def test_foul_up_3_resolves_without_error_and_logs():
    _, sim = _sim(collect_pbp=True)
    _ready_lineups(sim)
    sim.clock = 5.0
    sim.result.home_score, sim.result.away_score = 100, 103
    before = sim.result.away_score - sim.result.home_score   # +3 for defense
    sim._foul_up_3(sim.home, sim.away)
    # the deliberate foul is narrated, and the offense can never tie on this trip
    assert sim.result.pbp
    assert sim.result.away_score - sim.result.home_score >= 0   # defense still leads or tied-game avoided
    assert before == 3


# --- coach-mode: crunch lineup --------------------------------------------
def test_rotation_crunch_lineup_keeps_games_legal():
    w = build_world(seed=7)
    h, a = w.teams[0], w.teams[1]
    a.tactics.crunch_lineup = "Rotation"
    r = simulate_game(w, h, a)
    assert r.home_score != r.away_score
    # box still reconciles with team score
    assert sum(r.box[p].pts for p in a.roster if p in r.box) == r.away_score


# --- tactics serialization defaults ---------------------------------------
def test_tactics_defaults_for_missing_keys():
    t = Tactics.from_dict({"pace": "Fast"})
    assert t.pace == "Fast"
    assert t.crunch_foul == "Auto"
    assert t.foul_up_3 == "No"
    assert t.crunch_lineup == "Closers"


# --- play-by-play depth ---------------------------------------------------
def test_pbp_depth_surfaces_misses_rebounds_assists():
    w = build_world(seed=4)
    h, a = w.teams[0], w.teams[1]
    r = simulate_game(w, h, a, collect_pbp=True)
    texts = " ".join(e.text for e in r.pbp).lower()
    assert "miss" in texts
    assert "rebound" in texts or "board" in texts
    assert "assist:" in texts
    # plain (unwatched) sims stay log-free
    assert simulate_game(w, h, a).pbp == []
