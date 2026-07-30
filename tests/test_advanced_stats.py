"""Unit tests for advanced/derived stats (TS%, usage%, ORtg/DRtg)."""
from __future__ import annotations

from hoopsim.models import advanced
from hoopsim.models.stats import StatLine


def _line(**kw) -> StatLine:
    return StatLine(**kw)


def test_possessions_averages_both_sides():
    team = _line(fga=80, oreb=10, tov=12, fta=20)
    opp = _line(fga=84, oreb=8, tov=14, fta=16)
    est_team = 80 - 10 + 12 + 0.44 * 20
    est_opp = 84 - 8 + 14 + 0.44 * 16
    assert advanced.possessions(team, opp) == (est_team + est_opp) / 2


def test_possessions_falls_back_to_one_side_when_opp_empty():
    team = _line(fga=80, oreb=10, tov=12, fta=20)
    opp = StatLine()
    assert advanced.possessions(team, opp) == 80 - 10 + 12 + 0.44 * 20


def test_team_ortg_drtg_symmetry():
    team = _line(pts=100, fga=80, oreb=10, tov=12, fta=20)
    opp = _line(pts=95, fga=84, oreb=8, tov=14, fta=16)
    assert advanced.team_ortg(team, opp) == advanced.team_drtg(opp, team)
    assert advanced.team_drtg(team, opp) == advanced.team_ortg(opp, team)


def test_ratings_are_zero_with_no_possessions():
    empty = StatLine()
    assert advanced.team_ortg(empty, empty) == 0.0
    assert advanced.team_drtg(empty, empty) == 0.0
    assert advanced.pace(empty, empty) == 0.0


def test_usage_pct_zero_division_guards():
    team = _line(fga=80, fta=20, tov=12, secs=240 * 60)
    dnp = StatLine()
    assert advanced.usage_pct(dnp, team) == 0.0
    assert advanced.usage_pct(_line(fga=5, secs=600), StatLine()) == 0.0


def test_usage_pct_reasonable_for_a_normal_game():
    # Team totals for a single game: 5 players * 48 min = 240 team-minutes.
    team = _line(fga=80, fta=20, tov=12, secs=240 * 60)
    player = _line(fga=16, fta=4, tov=2, secs=32 * 60)
    usg = advanced.usage_pct(player, team)
    assert 0 < usg < 100


def test_player_ortg_proxy_falls_back_to_team_rating_for_dnp():
    team = _line(pts=100, fga=80, oreb=10, tov=12, fta=20)
    opp = _line(pts=95, fga=84, oreb=8, tov=14, fta=16)
    dnp = StatLine()
    assert advanced.player_ortg_proxy(dnp, team, opp) == advanced.team_ortg(team, opp)


def test_player_ortg_proxy_scales_with_relative_efficiency():
    team = _line(pts=100, fga=80, oreb=10, tov=12, fta=20)
    opp = _line(pts=95, fga=84, oreb=8, tov=14, fta=16)
    efficient = _line(pts=30, fga=15, fta=5, secs=1800)
    inefficient = _line(pts=8, fga=15, fta=5, secs=1800)
    assert advanced.player_ortg_proxy(efficient, team, opp) > advanced.player_ortg_proxy(inefficient, team, opp)


def test_player_drtg_proxy_falls_back_to_team_rating_when_no_minutes():
    team = _line(pts=100, fga=80, oreb=10, tov=12, fta=20, stl=8, blk=5, dreb=35, secs=240 * 60)
    opp = _line(pts=95, fga=84, oreb=8, tov=14, fta=16)
    dnp = StatLine()
    assert advanced.player_drtg_proxy(dnp, team, opp) == advanced.team_drtg(team, opp)


def test_player_drtg_proxy_rewards_defensive_activity():
    team = _line(pts=100, fga=80, oreb=10, tov=12, fta=20, stl=8, blk=5, dreb=35, secs=240 * 60)
    opp = _line(pts=95, fga=84, oreb=8, tov=14, fta=16)
    active = _line(stl=3, blk=2, dreb=8, secs=1800)
    passive = _line(stl=0, blk=0, dreb=1, secs=1800)
    # Lower DRtg is better defense.
    assert advanced.player_drtg_proxy(active, team, opp) < advanced.player_drtg_proxy(passive, team, opp)


def test_pace_matches_possessions_for_a_single_48_minute_game():
    team = _line(fga=80, oreb=10, tov=12, fta=20, secs=240 * 60)  # 5 players * 48 min
    opp = _line(fga=84, oreb=8, tov=14, fta=16, secs=240 * 60)
    poss = advanced.possessions(team, opp)
    assert advanced.pace(team, opp) == poss
