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


# --- coach-mode: situational lineup presets --------------------------------
def test_presets_offer_five_available_players_each():
    _, sim = _sim()
    _ready_lineups(sim)
    view = sim._build_view(sim.home, sim.away, sim.home)
    assert set(view.presets) == {"closers", "shooters", "stoppers", "ft"}
    avail = {pid for pid in sim.home.available if pid not in sim.home.unavailable}
    for key, five in view.presets.items():
        assert len(five) == 5 and len(set(five)) == 5
        assert set(five) <= avail


def test_presets_pick_the_right_skill_for_the_situation():
    _, sim = _sim()
    _ready_lineups(sim)
    view = sim._build_view(sim.home, sim.away, sim.home)
    players = sim.home.players
    # The FT unit can't be beaten on free-throw shooting by any available five.
    ft_sum = sum(players[pid].ratings["free_throw"] for pid in view.presets["ft"])
    avail = [pid for pid in sim.home.available if pid not in sim.home.unavailable]
    best_ft = sum(sorted((players[pid].ratings["free_throw"] for pid in avail),
                         reverse=True)[:5])
    assert ft_sum == best_ft
    # Closers are the five best by overall.
    best_ovr = sum(sorted((players[pid].overall for pid in avail), reverse=True)[:5])
    assert sum(players[pid].overall for pid in view.presets["closers"]) == best_ovr


def test_presets_skip_fouled_out_players():
    _, sim = _sim()
    _ready_lineups(sim)
    gone = sim.home.available[0]
    sim.home.unavailable.add(gone)
    view = sim._build_view(sim.home, sim.away, sim.home)
    for five in view.presets.values():
        assert gone not in five


# --- coach-mode: offensive sets --------------------------------------------
def test_inside_set_pushes_shots_to_the_rim():
    _, sim = _sim(coach=Coach())
    _ready_lineups(sim)
    shooter = sim.home.cache.players[0]
    sim._plan_possession(sim.home, sim.away, CoachOrders(offensive_set="motion"))
    base_rim = sum(sim._pick_shot_type(shooter, sim.home, putback=False) == "rim"
                   for _ in range(400))
    sim._plan_possession(sim.home, sim.away, CoachOrders(offensive_set="inside"))
    inside_rim = sum(sim._pick_shot_type(shooter, sim.home, putback=False) == "rim"
                     for _ in range(400))
    assert inside_rim > base_rim


def test_spread_set_arms_a_three_bias():
    _, sim = _sim(coach=Coach())
    sim._plan_possession(sim.home, sim.away, CoachOrders(offensive_set="spread"))
    assert sim._three_bias > 0.0
    # a plain motion set clears it again
    sim._plan_possession(sim.home, sim.away, CoachOrders(offensive_set="motion"))
    assert sim._three_bias == 0.0


def test_iso_set_concentrates_usage_on_the_top_option():
    _, sim = _sim(coach=Coach())
    _ready_lineups(sim)
    oc = sim.home.cache
    star = max(range(len(oc.players)), key=lambda i: oc.usage[i])
    sim._plan_possession(sim.home, sim.away, CoachOrders(offensive_set="motion"))
    base = sum(sim._pick_shooter(sim.home, oc, putback=False) == star for _ in range(600))
    sim._plan_possession(sim.home, sim.away, CoachOrders(offensive_set="iso"))
    iso = sum(sim._pick_shooter(sim.home, oc, putback=False) == star for _ in range(600))
    assert iso > base


def test_offensive_set_ignored_on_defense():
    # User coaches the defense: an offensive set order must not bias the opponent's offense.
    _, sim = _sim(coach=Coach())
    sim.coach_tid = sim.away.team.tid
    sim._plan_possession(sim.home, sim.away, CoachOrders(offensive_set="spread"))
    assert sim._three_bias == 0.0
    assert not sim._iso_set


# --- coach-mode: situation hint --------------------------------------------
def test_hint_is_situational_and_nonempty():
    _, sim = _sim()
    _ready_lineups(sim)
    sim.clock = 12.0
    sim.result.home_score, sim.result.away_score = 100, 102   # home (user) down 2
    off_hint = sim._build_view(sim.home, sim.away, sim.home).hint   # user on offense
    def_hint = sim._build_view(sim.away, sim.home, sim.home).hint   # user on defense
    assert off_hint and def_hint and off_hint != def_hint
    assert "2" in off_hint                                          # references the 2-point margin


# --- coach-mode: reactive free-throw sub window -----------------------------
def _bench(state):
    return [pid for pid in state.available
            if pid not in state.on_court and pid not in state.unavailable]


def test_ft_sub_window_offers_sub_only_view_and_applies_it():
    import pytest
    _, sim = _sim(coach=Coach())
    _ready_lineups(sim)
    sim.clock = 20.0                                          # inside the FT sub window (<=60s)
    sim.result.home_score, sim.result.away_score = 101, 100   # one-possession game
    sim.coach_tid = sim.home.team.tid                        # user coaches home (the defense here)
    # Home deliberately fouls away: the generator pauses before the final FT.
    driver = sim._drive_resolution(sim._intentional_foul_g(sim.away, sim.home))
    view = next(driver)
    assert view.sub_only and view.presets and _bench(sim.home)
    incoming = _bench(sim.home)[0]
    new_five = sim.home.on_court[:4] + [incoming]
    with pytest.raises(StopIteration):
        driver.send(CoachOrders(lineup=new_five))
    # the fresh five is on the floor for the live rebound + ensuing trip
    assert set(sim.home.on_court) == set(new_five)


def test_ft_sub_window_closed_outside_crunch():
    import pytest
    _, sim = _sim(coach=Coach())
    _ready_lineups(sim)
    sim.clock = 120.0                                        # outside the FT sub window
    sim.result.home_score, sim.result.away_score = 101, 100
    sim.coach_tid = sim.home.team.tid
    driver = sim._drive_resolution(sim._intentional_foul_g(sim.away, sim.home))
    with pytest.raises(StopIteration):                       # resolves with no sub prompt
        next(driver)


def test_ft_sub_window_closed_when_not_one_possession():
    _, sim = _sim(coach=Coach())
    _ready_lineups(sim)
    sim.clock = 20.0
    sim.result.home_score, sim.result.away_score = 110, 100   # 10 > FT_SUB_MARGIN
    sim.coach_tid = sim.home.team.tid
    assert not sim._ft_sub_window()


def test_sync_foul_paths_never_pause():
    # The synchronous wrappers (used by tests and non-coached sims) must fully resolve.
    _, sim = _sim(collect_pbp=True)
    _ready_lineups(sim)
    sim.clock = 15.0
    sim.result.home_score, sim.result.away_score = 100, 101
    sim._intentional_foul(sim.home, sim.away)               # returns, doesn't yield
    sim._foul_up_3(sim.home, sim.away)
    sim._resolve_possession(sim.home, sim.away)
    assert sim.result.pbp


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
