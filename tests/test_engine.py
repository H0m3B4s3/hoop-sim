"""Engine correctness: box-score reconciliation and realistic distributions."""
from __future__ import annotations

import statistics as st

from hoopsim.gen.leaguegen import build_world
from hoopsim.sim.engine import simulate_game


def _sim_sample(seed=4, n=120):
    w = build_world(seed=seed)
    teams = list(w.teams.values())
    results = []
    for _ in range(n):
        h, a = w.rng.sample(teams, 2)
        results.append((h, a, simulate_game(w, h, a)))
    return w, results


def test_boxscore_reconciles():
    w, results = _sim_sample()
    for h, a, r in results:
        # team score equals the sum of its players' points
        home_pts = sum(r.box[p].pts for p in h.roster if p in r.box)
        away_pts = sum(r.box[p].pts for p in a.roster if p in r.box)
        assert home_pts == r.home_score
        assert away_pts == r.away_score
        for line in r.box.values():
            assert line.pts == 2 * line.fgm + line.tpm + line.ftm   # 2*2PM+3*3PM+FTM
            assert 0 <= line.fgm <= line.fga
            assert 0 <= line.tpm <= line.tpa
            assert line.tpa <= line.fga                              # threes are FGAs
            assert 0 <= line.ftm <= line.fta
            assert line.pf <= 6
            assert line.secs >= 0


def test_no_ties_after_regulation():
    w, results = _sim_sample()
    for _, _, r in results:
        assert r.home_score != r.away_score


def test_scoring_in_realistic_band():
    w, results = _sim_sample(seed=8, n=200)
    scores = [s for _, _, r in results for s in (r.home_score, r.away_score)]
    mean = st.mean(scores)
    assert 104 <= mean <= 124, f"mean team score {mean:.1f} out of band"
    # Rare "unicorn" archetypes widen the upper tail (a stacked elite roster can erupt) without
    # moving the mean/median; the ceiling is a sanity bound against truly broken blowouts.
    assert min(scores) > 70 and max(scores) < 190


def test_minutes_sum_near_240():
    w, results = _sim_sample(seed=2, n=40)
    for h, a, r in results:
        for team in (h, a):
            total_min = sum(r.box[p].secs for p in team.roster if p in r.box) / 60.0
            # 48 min * 5 = 240, plus overtime; allow slack for rounding.
            assert 232 <= total_min <= 240 + r.overtimes * 25 + 6


def test_better_team_wins_more():
    w = build_world(seed=15)

    def strength(t):
        rs = sorted((w.players[p].overall for p in t.roster), reverse=True)[:8]
        return sum(rs) / len(rs)

    ts = sorted(w.teams.values(), key=strength)
    strong, weak = ts[-1], ts[0]
    wins = sum(simulate_game(w, strong, weak).home_score
               > simulate_game(w, strong, weak).away_score for _ in range(100))
    assert wins >= 70   # the clearly better team should dominate the head-to-head
