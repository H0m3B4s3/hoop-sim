"""Team power-rating (SRS + roster prior) tests."""
from __future__ import annotations

from hoopsim.gen.leaguegen import build_world
from hoopsim.sim import power
from hoopsim.sim import season as S


def _world(seed=1, games=30):
    w = build_world(seed=seed)
    w.user_team_id = 1
    w.season_games = games
    S.start_season(w)
    return w


def test_ratings_cover_every_team_and_rank_uniquely():
    w = _world()
    ratings = power.power_ratings(w)
    assert len(ratings) == len(w.teams)
    assert sorted(r.rank for r in ratings) == list(range(1, len(ratings) + 1))
    assert ratings[0].rank == 1
    # Best-first ordering.
    assert all(ratings[i].power >= ratings[i + 1].power for i in range(len(ratings) - 1))


def test_league_average_is_zero():
    w = _world(seed=4)
    ratings = power.power_ratings(w)
    mean = sum(r.power for r in ratings) / len(ratings)
    assert abs(mean) < 1e-6


def test_prior_dominates_before_any_games():
    """At gp == 0 the blended power equals the roster prior (de-meaned)."""
    w = build_world(seed=2)
    w.user_team_id = 1
    w.season_games = 30
    S.start_season(w)   # schedule built, nothing played yet
    ratings = power.power_map(w)
    priors = power.roster_priors(w)
    pmean = sum(priors.values()) / len(priors)
    for tid, r in ratings.items():
        assert abs(r.power - (priors[tid] - pmean)) < 1e-6
        assert r.srs == 0.0 or abs(r.srs) < 1e-6


def test_results_pull_rating_after_a_season():
    w = _world(seed=5, games=40)
    for _ in range(200):
        if S.regular_season_complete(w):
            break
        S.advance_one_day(w)
    ratings = power.power_map(w)
    teams = {t.tid: t for t in w.team_list()}
    # The best team by record should land clearly positive; the worst clearly negative.
    best = max(teams.values(), key=lambda t: t.win_pct)
    worst = min(teams.values(), key=lambda t: t.win_pct)
    assert ratings[best.tid].power > ratings[worst.tid].power
    assert ratings[best.tid].power > 0 > ratings[worst.tid].power


def test_proj_win_pct_monotonic_in_power():
    w = _world(seed=8)
    ratings = power.power_ratings(w)
    for i in range(len(ratings) - 1):
        assert ratings[i].proj_win_pct >= ratings[i + 1].proj_win_pct
