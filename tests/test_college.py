"""College-mode tests: generation, season, tournaments, eligibility, pipeline, finances, save."""
from __future__ import annotations

from hoopr.gen.collegegen import build_college_world
from hoopr.save.serialize import world_from_json, world_to_json
from hoopr.sim import college_tourney as CT
from hoopr.sim import season as S
from hoopr.systems import college_offseason as CO
from hoopr.systems import collegefin, recruiting


def _college_world(seed=1, economy="scholarship", games=12):
    w = build_college_world(seed=seed, economy=economy)
    w.user_team_id = 0
    w.season_games = games
    S.start_season(w)
    return w


def test_world_shape_and_toggle():
    w = build_college_world(seed=2, economy="nil")
    assert w.mode == "college"
    assert w.college_economy == "nil"
    assert len(w.teams) == 32                  # college programs
    assert len(w.other_teams) == 30            # background NBA
    assert len(w.recruits) > 0
    for t in w.teams.values():
        assert t.league == "college"
        assert len(t.roster) >= 11
        for pid in t.roster:
            assert 1 <= w.players[pid].class_year <= 4


def test_season_and_national_champion():
    w = _college_world(seed=3, games=12)
    while not S.regular_season_complete(w):
        S.advance_one_day(w)
    total_wins = sum(t.wins for t in w.teams.values())
    assert total_wins == len([g for g in w.schedule if not g.is_playoff])
    CT.start_college_postseason(w)
    guard = 0
    while not CT.college_postseason_complete(w):
        CT.advance_college_slate(w)
        guard += 1
        assert guard < 60
    champ = CT.national_champion(w)
    assert champ in w.teams


def test_eligibility_and_pipeline():
    w = _college_world(seed=4, games=12)
    while not S.regular_season_complete(w):
        S.advance_one_day(w)
    CT.start_college_postseason(w)
    while not CT.college_postseason_complete(w):
        CT.advance_college_slate(w)
    champ = CT.national_champion(w)
    nba_before = sum(len(t.roster) for t in w.other_team_list())
    summary = CO.pre_recruiting(w, champ)
    assert summary["declared"] > 0
    assert summary["drafted"] > 0
    # drafted players actually joined NBA rosters and became pros (class_year reset)
    drafted_pids = [r["pid"] for r in w.pipeline["results"]]
    for pid in drafted_pids:
        p = w.players[pid]
        assert p.class_year == 0
        assert p.team_id in w.other_teams
    nba_after = sum(len(t.roster) for t in w.other_team_list())
    assert nba_after >= nba_before - 30        # rosters churned but didn't collapse


def test_full_college_offseason_rolls_over():
    w = _college_world(seed=6, games=12)
    while not S.regular_season_complete(w):
        S.advance_one_day(w)
    CT.start_college_postseason(w)
    while not CT.college_postseason_complete(w):
        CT.advance_college_slate(w)
    CO.run_college_offseason(w, CT.national_champion(w))
    assert w.season_year == 2026
    assert w.phase == "regular_season"
    for t in w.teams.values():
        assert 11 <= len(t.roster) <= 13       # within scholarship limit


def test_scholarship_and_nil_finances():
    w = _college_world(seed=7, economy="scholarship")
    team = w.teams[0]
    assert collegefin.scholarships_used(team) == len(team.roster)
    # NIL economy: offering a deal consumes budget
    wn = build_college_world(seed=7, economy="nil")
    tn = wn.teams[0]
    pid = tn.roster[0]
    before = collegefin.nil_available(wn, tn)
    ok, _ = collegefin.offer_nil_deal(wn, tn, pid, min(before, 500_000))
    assert ok
    assert collegefin.nil_available(wn, tn) < before


def test_recruiting_signs_into_open_spots():
    w = _college_world(seed=8)
    # open spots on several programs
    for tid in range(6):
        team = w.teams[tid]
        for pid in list(team.roster)[-3:]:
            team.remove_player(pid)
            w.players[pid].team_id = None
    summary = recruiting.resolve_recruiting(w, {})
    assert summary["total"] > 0


def test_college_save_round_trip():
    w = _college_world(seed=9, games=12)
    while not S.regular_season_complete(w):
        S.advance_one_day(w)
    CT.start_college_postseason(w)
    CT.advance_college_slate(w)
    once = world_to_json(w)
    w2 = world_from_json(once)
    assert world_to_json(w2) == once
    assert w2.mode == "college"
    assert len(w2.other_teams) == len(w.other_teams)
    assert w2.bracket == w.bracket
