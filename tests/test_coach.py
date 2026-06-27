"""Coach-mode end-game behaviors and play-by-play depth."""
from __future__ import annotations

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.tactics import Tactics
from hoopsim.sim.coach import Coach, CoachOrders
from hoopsim.sim.engine import DRAW_PLAY_BONUS, GameSim, simulate_game


def _sim(seed=1, *, collect_pbp=False, coach=None):
    w = build_world(seed=seed)
    h, a = w.teams[0], w.teams[1]
    sim = GameSim(w, h, a, collect_pbp=collect_pbp, coach=coach,
                  coach_tid=h.tid if coach is not None else None)
    sim.quarter = sim.periods            # final period for end-game logic
    return w, sim


class _StubCoach(Coach):
    """Returns a canned CoachOrders so engine wiring can be tested headlessly."""
    def __init__(self, orders):
        self.orders = orders
    def decide(self, view):
        return self.orders


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


# --- interactive live coaching --------------------------------------------
def test_coach_engaged_window():
    _, sim = _sim(coach=Coach())
    sim.result.home_score, sim.result.away_score = 100, 98   # within margin
    sim.clock = 60.0
    assert sim._coach_engaged(sim.home, sim.away)
    sim.clock = 200.0                                        # too early
    assert not sim._coach_engaged(sim.home, sim.away)
    sim.clock = 60.0
    sim.result.away_score = 70                               # blowout (margin > 12)
    assert not sim._coach_engaged(sim.home, sim.away)
    sim.quarter = 1                                          # not the final period
    sim.result.away_score = 98
    assert not sim._coach_engaged(sim.home, sim.away)


def test_coach_timeout_consumes_and_arms_draw_play():
    coach = _StubCoach(CoachOrders(timeout=True))
    _, sim = _sim(coach=coach)
    _ready_lineups(sim)
    start = sim.home.timeouts
    for pid in sim.home.on_court:
        sim.home.fatigue[pid] = 50.0
    sim._consult_coach(sim.home, sim.away)
    assert sim.home.timeouts == start - 1
    assert sim._draw_play_tid == sim.home.team.tid
    assert all(sim.home.fatigue[pid] < 50.0 for pid in sim.home.on_court)  # rested
    # the armed possession gets the make boost, then it's spent
    sim._resolve_possession(sim.home, sim.away)
    assert sim._draw_play_tid is None


def test_coach_timeout_ignored_when_none_left():
    coach = _StubCoach(CoachOrders(timeout=True))
    _, sim = _sim(coach=coach)
    _ready_lineups(sim)
    sim.home.timeouts = 0
    sim._consult_coach(sim.home, sim.away)
    assert sim.home.timeouts == 0
    assert sim._draw_play_tid is None


def test_coach_forced_foul_overrides_auto():
    # The user's defense (away) is *ahead*, so auto would never intentionally foul (deterministic,
    # independent of the crunch-foul RNG roll) — a clean baseline to prove the forced order wins.
    auto = _StubCoach(CoachOrders(defensive_foul="auto"))
    _, sim = _sim(coach=auto)
    sim.coach_tid = sim.away.team.tid                       # user coaches the defense
    sim.clock = 20.0
    sim.result.home_score, sim.result.away_score = 100, 105   # defense (away) leads by 5
    intentional, _, _ = sim._plan_possession(sim.home, sim.away, CoachOrders(defensive_foul="auto"))
    assert not intentional
    intentional, _, _ = sim._plan_possession(sim.home, sim.away, CoachOrders(defensive_foul="foul"))
    assert intentional


def test_coach_hold_drains_clock_to_last_shot():
    _, sim = _sim(coach=Coach())
    sim.clock = 18.0
    _, _, secs = sim._plan_possession(sim.home, sim.away, CoachOrders(tempo="hold"))
    assert 15.0 <= secs <= 17.0                             # milks most of the clock
    # never holds past the shot clock
    sim.clock = 90.0
    _, _, secs = sim._plan_possession(sim.home, sim.away, CoachOrders(tempo="hold"))
    assert secs <= sim.shot_clock


def test_coach_quick3_is_fast_and_forces_threes():
    _, sim = _sim(coach=Coach())
    sim.clock = 40.0
    for _ in range(20):
        _, _, secs = sim._plan_possession(sim.home, sim.away, CoachOrders(tempo="quick3"))
        assert 3.0 <= secs <= 6.0
    # quick3 arms a strong bias toward shooting a three this trip
    assert sim._three_bias > 0.5
    _ready_lineups(sim)
    shooter = sim.home.cache.players[0]
    threes = sum(sim._pick_shot_type(shooter, sim.home, putback=False) == "three"
                 for _ in range(200))
    assert threes > 120                                     # ~70% forced threes


def test_coach_bleed_chews_shot_clock():
    _, sim = _sim(coach=Coach())
    sim.clock = 200.0                                       # plenty of game clock left
    for _ in range(20):
        _, _, secs = sim._plan_possession(sim.home, sim.away, CoachOrders(tempo="bleed"))
        assert sim.shot_clock - 4.0 <= secs <= sim.shot_clock   # ~20-23s, milks the shot clock
    # a normal possession clears the three bias again
    sim._plan_possession(sim.home, sim.away, CoachOrders(tempo="normal"))
    assert sim._three_bias == 0.0


def test_coach_lineup_lock_is_honored():
    coach = Coach()
    _, sim = _sim(coach=coach)
    _ready_lineups(sim)
    bench = [pid for pid in sim.home.available if pid not in sim.home.on_court]
    assert bench
    new_five = sim.home.on_court[:4] + [bench[0]]
    sim.coach = _StubCoach(CoachOrders(lineup=new_five))
    sim._consult_coach(sim.home, sim.away)
    assert set(sim.home.on_court) == set(new_five)
    # a normal rotation re-pick keeps honoring the lock
    sim.home.choose_lineup(sim.game_secs)
    assert set(sim.home.on_court) == set(new_five)


def test_timeouts_initialized_from_format():
    _, sim = _sim()
    assert sim.home.timeouts == 7        # nba default
    assert sim.shot_clock == 24.0


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
