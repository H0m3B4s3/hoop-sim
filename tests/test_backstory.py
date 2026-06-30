"""Launch backstory: fabricated veteran careers + a retired-legends cohort, deterministically."""
from __future__ import annotations

from hoopsim.gen.leaguegen import build_world
from hoopsim.systems import legacy


def test_backstory_does_not_perturb_the_roster():
    """The dedicated rng must leave the league byte-identical — same rosters and ratings."""
    a = build_world(seed=321, backstory=True)
    b = build_world(seed=321, backstory=False)
    assert {t.tid: list(t.roster) for t in a.team_list()} == {t.tid: list(t.roster) for t in b.team_list()}
    shared = {pid for pid in a.players if pid in b.players}
    assert {pid: a.players[pid].overall for pid in shared} == {pid: b.players[pid].overall for pid in shared}
    # ...but only the backstory world has fabricated history.
    assert any(p.career for p in a.players.values())
    assert not any(p.career for p in b.players.values())


def test_backstory_is_deterministic():
    a = build_world(seed=99)
    b = build_world(seed=99)
    assert [s["name"] for s in a.hall_of_fame] == [s["name"] for s in b.hall_of_fame]
    # a sample veteran's fabricated arc matches
    pid = next(pid for pid, p in a.players.items() if p.career)
    assert a.players[pid].career == b.players[pid].career
    assert a.players[pid].draft == b.players[pid].draft


def test_veterans_get_consistent_careers():
    w = build_world(seed=7)
    for p in w.players.values():
        if p.experience > 0 and p.class_year == 0 and p.career:
            # arc length matches pro experience, so aging/salary stay coherent
            assert len(p.career) == p.experience
            # the final fabricated season lands near the player's current rating
            assert abs(p.career[-1]["ovr"] - p.overall) <= 6
            # career totals reconcile through the legacy résumé
            r = legacy.resume(w, p)
            assert r["totals"]["pts"] >= 0 and r["peak_ovr"] >= p.overall


def test_rookies_have_no_fabricated_history():
    w = build_world(seed=11)
    rookies = [p for p in w.players.values() if p.experience == 0]
    assert rookies
    assert all(not p.career and not p.accolades for p in rookies)


def test_legends_seed_hall_of_fame_and_records():
    w = build_world(seed=5)
    assert w.hall_of_fame, "expected a retired-legends cohort at launch"
    # legends are self-contained snapshots, not active players
    legend = w.hall_of_fame[0]
    assert legend["pid"] not in w.players
    assert legend["hof"] and legend["hof_score"] >= legacy.HOF_THRESHOLD
    assert legend["totals"]["pts"] > 0
    # all-time leaderboard is populated and ranked
    board = legacy.leaderboards(w, "pts", limit=10)
    assert len(board) >= 10
    pts = [r["totals"]["pts"] for r in board]
    assert pts == sorted(pts, reverse=True)


def test_draft_info_present_and_well_formed():
    w = build_world(seed=8)
    n_teams = len(w.teams)
    drafted = [p for p in w.players.values() if p.draft]
    assert drafted, "expected some veterans to have a fabricated draft slot"
    for p in drafted:
        d = p.draft
        assert 1 <= d["pick"] <= 2 * n_teams
        assert d["round"] in (1, 2)
        assert d["team"]


def test_backstory_survives_save_round_trip():
    from hoopsim.models.world import World
    w = build_world(seed=13)
    w2 = World.from_dict(w.to_dict())
    assert w2.hall_of_fame == w.hall_of_fame
    pid = next(pid for pid, p in w.players.items() if p.career)
    assert w2.players[pid].career == w.players[pid].career
    assert w2.players[pid].draft == w.players[pid].draft
    assert w2.players[pid].accolades == w.players[pid].accolades
