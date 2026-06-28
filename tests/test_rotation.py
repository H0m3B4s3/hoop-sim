"""User-controlled rotation: pinning who plays feeds straight into minute targets."""
from __future__ import annotations

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.player import Injury
from hoopsim.models.team import (MAX_ROTATION, auto_set_lineup, rotation_pool,
                                  set_auto_minutes)


def _team(seed=7):
    w = build_world(seed=seed)
    team = w.team_list()[0]
    auto_set_lineup(team, w.players)
    return w, team


def _bench(w, team):
    bench = [w.players[pid] for pid in team.roster if pid not in team.starters]
    bench.sort(key=lambda p: p.overall, reverse=True)
    return bench


def test_auto_rotation_zeroes_deep_bench():
    """With no manual rotation, the lowest-overall reserves get no minutes."""
    w, team = _team()
    assert team.rotation == []
    minutes = team.minutes_target
    # The very worst bench player sits outside the coach's rotation_size.
    worst = _bench(w, team)[-1]
    assert minutes.get(worst.pid, 0) == 0


def test_pinned_rookie_plays_over_unpinned_veteran():
    """Pinning a low-overall reserve gives him minutes; unpinned reserves drop to zero."""
    w, team = _team()
    bench = _bench(w, team)
    veteran, rookie = bench[0], bench[-1]          # highest- and lowest-overall reserves
    assert veteran.overall > rookie.overall

    team.rotation = [rookie.pid]
    set_auto_minutes(team, w.players)

    assert team.minutes_target.get(rookie.pid, 0) > 0
    # Every reserve who isn't a starter and isn't pinned sits at the end of the bench.
    for p in bench:
        if p.pid != rookie.pid:
            assert team.minutes_target.get(p.pid, 0) == 0


def test_rotation_pool_backfills_when_injuries_thin_the_pins():
    """If availability drops the pinned group below five, depth backfills to a fieldable lineup."""
    w, team = _team()
    bench = _bench(w, team)
    team.rotation = [bench[-1].pid]                # only one pinned reserve -> 6 total
    # Injure three starters so only 2 starters + 1 reserve (= 3) remain available.
    for pid in team.starters[:3]:
        w.players[pid].injury = Injury("knock", games_remaining=10)
    pool = rotation_pool(team, w.players)
    assert len(pool) >= 5                          # backfilled from healthy depth


def test_rotation_cap_and_persistence_round_trip():
    w, team = _team()
    bench = _bench(w, team)
    team.rotation = [p.pid for p in bench[:3]]
    set_auto_minutes(team, w.players)
    assert sum(1 for m in team.minutes_target.values() if m > 0) <= MAX_ROTATION

    from hoopsim.models.team import Team
    restored = Team.from_dict(team.to_dict())
    assert restored.rotation == team.rotation
