"""World-generation sanity checks."""
from __future__ import annotations

from hoopsim.config import NUM_TEAMS, RATING_MAX, RATING_MIN, ROSTER_MIN
from hoopsim.gen.leaguegen import build_world
from hoopsim.models.attributes import ALL_RATINGS
from hoopsim.models.team import team_salary


def test_world_shape():
    w = build_world(seed=7)
    assert len(w.teams) == NUM_TEAMS
    for team in w.teams.values():
        assert len(team.roster) >= ROSTER_MIN
        assert len(team.starters) == 5
        assert sum(team.minutes_target.values()) > 200      # near 240 player-minutes
        # jerseys unique within a team
        jerseys = [w.players[pid].jersey for pid in team.roster]
        assert len(jerseys) == len(set(jerseys))


def test_ratings_in_range():
    w = build_world(seed=11)
    for p in w.players.values():
        assert all(RATING_MIN <= p.ratings[r] <= RATING_MAX for r in ALL_RATINGS)
        assert RATING_MIN <= p.overall <= RATING_MAX
        assert p.overall <= p.potential <= RATING_MAX


def test_payrolls_are_sane():
    w = build_world(seed=3)
    for team in w.teams.values():
        salary = team_salary(team, w.players)
        assert 40_000_000 < salary < 230_000_000


def test_determinism_same_seed():
    a = build_world(seed=99)
    b = build_world(seed=99)
    assert [p.name for p in a.players.values()] == [p.name for p in b.players.values()]
    assert [p.overall for p in a.players.values()] == [p.overall for p in b.players.values()]


def test_free_agents_have_no_team():
    w = build_world(seed=5)
    for pid in w.free_agents:
        assert w.players[pid].team_id is None
