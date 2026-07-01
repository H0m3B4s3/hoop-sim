"""Season momentum: how morale moves after a game, and the team form read."""
from __future__ import annotations

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.stats import StatLine
from hoopsim.sim.boxscore import GameResult
from hoopsim.systems.momentum import (
    CHEM_RETENTION, MORALE_MAX, MORALE_MIN, game_score, offseason_reset, update_morale,
)
from hoopsim.models.team import pair_key
from hoopsim.sim.ratings import FULL_CHEM_SECS, familiarity_realization


def _result(world, home, away, home_pts, away_pts, *, star_line=None):
    """A finished game: every player gets a modest line, optionally a star line for home[0]."""
    res = GameResult(home_tid=home.tid, away_tid=away.tid,
                     home_score=home_pts, away_score=away_pts)
    for team in (home, away):
        for pid in team.roster[:9]:                       # a 9-man rotation gets minutes
            res.box[pid] = StatLine(gp=1, secs=24 * 60, pts=10, fgm=4, fga=9, ast=2, dreb=3)
    if star_line is not None:
        res.box[home.roster[0]] = star_line
    return res


def test_win_lifts_loss_sinks():
    w = build_world(seed=11)
    home, away = w.teams[0], w.teams[1]
    for p in w.players.values():
        p.morale = 70
    update_morale(w, home, away, _result(w, home, away, 112, 100))
    assert w.players[home.roster[0]].morale > 70      # winner's morale climbs
    assert w.players[away.roster[0]].morale < 70      # loser's slips


def test_mean_reversion_pulls_toward_baseline():
    w = build_world(seed=11)
    home, away = w.teams[0], w.teams[1]
    star = home.roster[0]
    w.players[star].morale = 99
    # A neutral-ish result (close loss, ordinary line) should let an inflated morale settle down.
    for _ in range(8):
        update_morale(w, home, away, _result(w, home, away, 100, 101))
    assert w.players[star].morale < 99


def test_injured_player_only_drifts():
    from hoopsim.models.player import Injury
    w = build_world(seed=11)
    home, away = w.teams[0], w.teams[1]
    p = w.players[home.roster[0]]
    p.morale = 50
    p.injury = Injury("sprain", 5, "moderate")
    update_morale(w, home, away, _result(w, home, away, 130, 90))  # big win he didn't play in
    # He drifts up toward baseline (reversion) but isn't credited with the blowout.
    assert 50 < p.morale <= 70


def test_healthy_dnp_drags_relative_and_sours_when_losing():
    w = build_world(seed=11)
    home, away = w.teams[0], w.teams[1]
    starter, deep_bench = home.roster[0], home.roster[12]   # rotation vs no minutes
    for pid in (starter, deep_bench):
        w.players[pid].morale = 70
    for _ in range(5):                                      # team keeps winning
        update_morale(w, home, away, _result(w, home, away, 110, 104))
    # Not playing keeps a healthy player behind the contributors, even on a winner.
    assert w.players[deep_bench].morale < w.players[starter].morale

    # And on a losing team, riding the bench clearly sours him.
    w.players[deep_bench].morale = 70
    for _ in range(5):
        update_morale(w, away, home, _result(w, away, home, 110, 104))  # home now loses
    assert w.players[deep_bench].morale < 70


def test_morale_stays_in_bounds():
    w = build_world(seed=11)
    home, away = w.teams[0], w.teams[1]
    for _ in range(40):
        update_morale(w, home, away, _result(w, home, away, 140, 80))   # relentless blowouts
        update_morale(w, away, home, _result(w, away, home, 140, 80))
    for p in w.players.values():
        if p.team_id is not None:
            assert MORALE_MIN <= p.morale <= MORALE_MAX


def test_offseason_reset_carries_core_rusts_thin_pairs():
    w = build_world(seed=11)
    t = w.teams[0]
    a, b, c, d = t.roster[0], t.roster[1], t.roster[2], t.roster[3]
    t.chemistry = {
        pair_key(a, b): FULL_CHEM_SECS * 4,    # a heavy, season-long core pairing
        pair_key(c, d): FULL_CHEM_SECS * 0.2,  # a thin, lightly-used pairing
    }
    offseason_reset(w)
    # The core returns fully gelled; the thin pairing rusts toward cold.
    assert familiarity_realization(t.chemistry[pair_key(a, b)]) == 1.0
    assert familiarity_realization(t.chemistry[pair_key(c, d)]) < 1.0
    assert t.chemistry[pair_key(c, d)] == FULL_CHEM_SECS * 0.2 * CHEM_RETENTION


def test_offseason_reset_drifts_morale_to_baseline():
    w = build_world(seed=11)
    for p in w.players.values():
        p.morale = 95
    offseason_reset(w)
    # A swaggering 95 settles back toward (but not all the way to) baseline.
    p = next(iter(w.players.values()))
    assert 70 < p.morale < 95


def test_game_score_rewards_production():
    big = StatLine(pts=30, fgm=11, fga=18, ast=8, dreb=7, stl=2)
    small = StatLine(pts=2, fgm=1, fga=8, tov=4, pf=4)
    assert game_score(big) > game_score(small)
