"""Season scheduling, standings, and playoff integration tests."""
from __future__ import annotations

from collections import Counter

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.league import conference_standings
from hoopsim.sim import playoffs as P
from hoopsim.sim import season as S


def _quick_world(seed=1, games=14):
    w = build_world(seed=seed)
    w.user_team_id = 1
    w.season_games = games
    S.start_season(w)
    return w


def test_schedule_is_balanced():
    w = _quick_world(games=20)
    counts = Counter()
    for g in w.schedule:
        if not g.is_playoff:
            counts[g.home] += 1
            counts[g.away] += 1
    assert set(counts.values()) == {20}            # every team plays exactly N games
    # no team plays twice on the same day
    for day in range(20):
        playing = [t for g in w.schedule if g.day == day for t in (g.home, g.away)]
        assert len(playing) == len(set(playing))


def test_wins_equal_games_after_season():
    w = _quick_world(seed=3, games=16)
    while not S.regular_season_complete(w):
        S.advance_one_day(w)
    total_wins = sum(t.wins for t in w.teams.values())
    total_games = len([g for g in w.schedule if not g.is_playoff])
    assert total_wins == total_games
    for t in w.teams.values():
        assert t.wins + t.losses == w.season_games


def test_standings_ordered_by_win_pct():
    w = _quick_world(seed=4, games=16)
    while not S.regular_season_complete(w):
        S.advance_one_day(w)
    east = conference_standings(w.team_list(), "East")
    pcts = [t.win_pct for t in east]
    assert pcts == sorted(pcts, reverse=True)


def test_injuries_stay_reasonable():
    w = _quick_world(seed=7, games=20)
    while not S.regular_season_complete(w):
        S.advance_one_day(w)
    injured = sum(1 for p in w.players.values() if p.injury)
    assert injured < 60          # not a leaguewide epidemic


def test_playoffs_produce_a_champion():
    w = _quick_world(seed=9, games=14)
    while not S.regular_season_complete(w):
        S.advance_one_day(w)
    P.start_playoffs(w)
    guard = 0
    while not P.playoffs_complete(w):
        P.advance_playoff_slate(w)
        guard += 1
        assert guard < 100
    champ = P.champion(w)
    assert champ in w.teams
    # champion must have actually won the Finals series in the bracket history
    finals = [s for s in w.bracket["all_series"] if s["round"] == "Finals"]
    assert finals and finals[0]["winner"] == champ
