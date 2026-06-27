"""Draft, development, and offseason-rollover tests."""
from __future__ import annotations

from hoopr.config import NUM_TEAMS, ROSTER_MAX, ROSTER_MIN
from hoopr.gen.leaguegen import build_world
from hoopr.sim import playoffs as P
from hoopr.sim import season as S
from hoopr.systems import development, draft_system, offseason


def _played_world(seed=1, games=14):
    w = build_world(seed=seed)
    w.user_team_id = 1
    w.season_games = games
    S.start_season(w)
    while not S.regular_season_complete(w):
        S.advance_one_day(w)
    P.start_playoffs(w)
    while not P.playoffs_complete(w):
        P.advance_playoff_slate(w)
    return w


def test_rookie_salary_monotonic():
    salaries = [draft_system.rookie_salary(p) for p in range(1, 61)]
    assert salaries == sorted(salaries, reverse=True)
    assert salaries[0] > salaries[-1]


def test_draft_order_and_completion():
    w = _played_world(seed=2)
    champ = P.champion(w)
    offseason.pre_draft(w, champ)
    dc = draft_system.setup_draft(w)
    assert dc.total_picks == 2 * NUM_TEAMS
    # The worst team is a non-playoff team, so it lands in the lottery (the first 14 R1 picks).
    # It can't be pinned to a specific top pick — the lottery is weighted-random, not deterministic.
    worst = min(w.team_list(), key=lambda t: t.win_pct)
    assert worst.tid in dc.order[:14]
    draft_system.auto_complete_draft(w)
    assert dc.complete
    assert len(dc.picks_made) == dc.total_picks


def test_draft_order_honors_traded_pick():
    w = _played_world(seed=2)
    champ = P.champion(w)
    offseason.pre_draft(w, champ)
    # Team B trades its current-year first-rounder to team A before the draft is set up.
    a, b = w.teams[0], w.teams[1]
    pick = w.find_pick(w.season_year, 1, b.tid)
    pick.owner_tid = a.tid
    dc = draft_system.setup_draft(w)
    # the slot is still B's position, but A is the one selecting there
    slot = dc.origins.index(b.tid)
    assert dc.origins[slot] == b.tid
    assert dc.order[slot] == a.tid


def test_roll_draft_picks_keeps_window_and_replenishes():
    from hoopr.config import FUTURE_PICK_YEARS
    w = build_world(seed=5)
    base_year = w.season_year
    # simulate the offseason year advance + roll
    w.season_year += 1
    draft_system.roll_draft_picks(w)
    years = {p.year for p in w.draft_picks}
    assert min(years) == base_year + 1
    assert max(years) == base_year + FUTURE_PICK_YEARS
    # window stays the same size and every team again owns its far-future picks
    assert len(w.draft_picks) == len(w.teams) * FUTURE_PICK_YEARS * 2


def test_full_offseason_keeps_rosters_legal():
    w = _played_world(seed=4)
    champ = P.champion(w)
    summary = offseason.run_offseason(w, champ)
    assert summary["draft"]["picks"] == 2 * NUM_TEAMS
    assert w.season_year == 2026
    for t in w.team_list():
        assert ROSTER_MIN <= len(t.roster) <= ROSTER_MAX
    # rookies actually landed on rosters
    rookies = [p for p in w.players.values()
               if p.contract.is_rookie_scale and p.team_id is not None]
    assert len(rookies) >= NUM_TEAMS


def test_development_direction():
    w = build_world(seed=6)
    young_up = old_down = young_n = old_n = 0
    for p in list(w.players.values()):
        if p.age <= 21 and p.potential - p.overall >= 6:
            young_n += 1
            if development.develop_player(p, w.rng) >= 0:
                young_up += 1
        elif p.age >= 34:
            old_n += 1
            if development.develop_player(p, w.rng) <= 0:
                old_down += 1
    # the strong majority of high-upside youngsters improve; most old players decline
    assert young_n == 0 or young_up / young_n >= 0.8
    assert old_n == 0 or old_down / old_n >= 0.7
