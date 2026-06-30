"""Role tags (sixth man / defensive ace / closer) bias the rotation and closing lineups."""
from __future__ import annotations

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.player import Injury
from hoopsim.models.team import (
    ROLE_TAGS, Team, auto_set_lineup, role_pid, rotation_pool, set_auto_minutes,
)
from hoopsim.sim.engine import GameSim, _team_offense_strength, simulate_game


def _team(seed=7):
    w = build_world(seed=seed)
    team = w.team_list()[0]
    auto_set_lineup(team, w.players)
    return w, team


def _reserves(w, team):
    """Non-starters, best-first."""
    bench = [w.players[pid] for pid in team.roster if pid not in team.starters]
    bench.sort(key=lambda p: p.overall, reverse=True)
    return bench


# -- model plumbing ---------------------------------------------------------
def test_roles_round_trip():
    w, team = _team()
    bench = _reserves(w, team)
    team.roles = {"sixth_man": bench[0].pid, "closer": team.starters[0]}
    restored = Team.from_dict(team.to_dict())
    assert restored.roles == team.roles


def test_remove_player_clears_role():
    w, team = _team()
    pid = _reserves(w, team)[0].pid
    team.roles["sixth_man"] = pid
    team.remove_player(pid)
    assert "sixth_man" not in team.roles


def test_role_pid_ignores_injured_or_off_roster():
    w, team = _team()
    pid = _reserves(w, team)[0].pid
    team.roles["defensive_ace"] = pid
    assert role_pid(team, "defensive_ace", w.players) == pid
    w.players[pid].injury = Injury("knock", games_remaining=5)
    assert role_pid(team, "defensive_ace", w.players) is None


# -- sixth man --------------------------------------------------------------
def test_sixth_man_tops_the_bench_queue():
    """A tagged sixth man draws more minutes than any other reserve, even a higher-rated one."""
    w, team = _team()
    bench = _reserves(w, team)
    # Tag a *lower-rated* reserve so the boost, not raw overall, is what lifts him.
    sixth = bench[2]
    team.roles["sixth_man"] = sixth.pid
    set_auto_minutes(team, w.players)
    sixth_min = team.minutes_target.get(sixth.pid, 0)
    assert sixth_min > 0
    for p in bench:
        if p.pid != sixth.pid:
            assert team.minutes_target.get(p.pid, 0) <= sixth_min


def test_sixth_man_forced_into_rotation_when_outside_auto_cut():
    """Even a deep reserve who'd miss the automatic rotation plays if tagged sixth man."""
    w, team = _team()
    worst = _reserves(w, team)[-1]
    assert team.minutes_target.get(worst.pid, 0) == 0   # normally sits
    team.roles["sixth_man"] = worst.pid
    set_auto_minutes(team, w.players)
    assert worst.pid in {p.pid for p in rotation_pool(team, w.players)}
    assert team.minutes_target.get(worst.pid, 0) > 0


# -- closer -----------------------------------------------------------------
def test_closer_overrides_clutch_lineup():
    """A tagged closer takes the floor to close even if he's a low-rated reserve."""
    w, team = _team()
    other = w.team_list()[1]
    worst = _reserves(w, team)[-1]
    gs = GameSim(w, team, other)
    gs.home.choose_lineup(0.0, clutch=True)
    assert worst.pid not in gs.home.on_court        # not a closer yet
    team.roles["closer"] = worst.pid
    gs.home.choose_lineup(0.0, clutch=True)
    assert worst.pid in gs.home.on_court            # the role pulls him onto the floor


def test_fouled_out_closer_does_not_play():
    w, team = _team()
    other = w.team_list()[1]
    worst = _reserves(w, team)[-1]
    team.roles["closer"] = worst.pid
    gs = GameSim(w, team, other)
    gs.home.unavailable.add(worst.pid)              # fouled out / injured
    gs.home.choose_lineup(0.0, clutch=True)
    assert worst.pid not in gs.home.on_court


# -- defensive ace ----------------------------------------------------------
def test_team_offense_strength_orders_teams():
    w = build_world(seed=5)
    other = w.team_list()[1]
    gs = GameSim(w, w.team_list()[0], other)
    strengths = []
    for t in w.team_list():
        strengths.append(_team_offense_strength(GameSim(w, t, other).home))
    assert 0.0 <= min(strengths) <= max(strengths) <= 1.0
    assert max(strengths) > min(strengths)          # teams genuinely differ


def _shift_offense(team, players, delta):
    for pid in team.roster:
        r = players[pid].ratings
        for k in ("finishing", "three_point", "mid_range"):
            r[k] = max(1, min(99, r[k] + delta))


def test_defensive_ace_earns_minutes_vs_strong_offense():
    """The ace logs more minutes against a strong offense than against a weak one."""
    strong_secs = weak_secs = 0.0
    for seed in range(6):
        for delta, is_strong in ((+18, True), (-18, False)):
            w = build_world(seed=seed)
            user, opp = w.team_list()[0], w.team_list()[1]
            auto_set_lineup(user, w.players)
            ace = _reserves(w, user)[0]             # a rotation reserve, not a starter
            user.roles["defensive_ace"] = ace.pid
            _shift_offense(opp, w.players, delta)
            result = simulate_game(w, user, opp)
            secs = result.box[ace.pid].secs if ace.pid in result.box else 0.0
            if is_strong:
                strong_secs += secs
            else:
                weak_secs += secs
    assert strong_secs > weak_secs


# -- constants sanity -------------------------------------------------------
def test_role_tags_known():
    assert set(ROLE_TAGS) == {"sixth_man", "defensive_ace", "closer"}
