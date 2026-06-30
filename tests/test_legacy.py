"""Career legacy: accolade accrual, résumés, milestones, the Hall of Fame, and leaderboards."""
from __future__ import annotations

from hoopsim.config import RETIREMENT_AGE
from hoopsim.gen.leaguegen import build_world
from hoopsim.models.world import World
from hoopsim.sim import playoffs as P
from hoopsim.sim import season as S
from hoopsim.systems import legacy, offseason


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


def _star_career(years=15, ppg=25.0):
    return [{"year": 2010 + i, "team": "AAA", "gp": 75, "ppg": ppg,
             "rpg": 7.0, "apg": 7.0, "ovr": 89} for i in range(years)]


# -- career math ------------------------------------------------------------
def test_career_totals_reconcile():
    totals = legacy.career_totals(_star_career(years=4, ppg=20.0))
    assert totals["gp"] == 300                       # 4 * 75
    assert totals["pts"] == 6000                     # 300 * 20
    assert totals["ppg"] == 20.0


def test_crossed_milestones_detects_thresholds():
    crossed = legacy.crossed_milestones({"pts": 9800}, {"pts": 10200})
    assert {"stat": "pts", "noun": "point", "value": 10000} in crossed
    # nothing crossed when both sides are on the same side of every threshold
    assert legacy.crossed_milestones({"pts": 10200}, {"pts": 10400}) == []


# -- résumé & HoF score -----------------------------------------------------
def test_resume_and_hof_for_a_star():
    w = build_world(seed=2)
    p = next(iter(w.players.values()))
    p.career = _star_career()
    p.accolades = {"mvp": 2, "all_league": 6, "champion": 2}
    r = legacy.resume(w, p)
    assert r["seasons"] == 15
    assert r["peak_ovr"] >= 89
    assert r["totals"]["pts"] == 15 * 75 * 25
    assert r["hof"] is True


def test_role_player_misses_hof():
    w = build_world(seed=2)
    p = next(iter(w.players.values()))
    p.career = [{"year": 2010 + i, "team": "BBB", "gp": 50, "ppg": 5.0,
                 "rpg": 2.0, "apg": 1.0, "ovr": 71} for i in range(8)]
    p.accolades = {}
    assert legacy.resume(w, p)["hof"] is False


# -- accolade accrual -------------------------------------------------------
def test_record_accolades_ticks_winners():
    w = build_world(seed=4, backstory=False)        # clean slate — no fabricated accolades
    champ = w.team_list()[0]
    for pid in champ.roster:
        w.players[pid].season.gp = 10                # qualify for the champion tally
    mvp = champ.roster[0]
    al = champ.roster[1]
    awards = {
        "mvp": {"pid": mvp},
        "all_league": [[{"pid": al}]],
        "leaders": {"pts": {"pid": mvp}},
    }
    legacy.record_accolades(w, awards, champ.tid)
    assert w.players[mvp].accolades["mvp"] == 1
    assert w.players[mvp].accolades["scoring_title"] == 1
    assert w.players[mvp].accolades["champion"] == 1
    assert w.players[al].accolades["all_league"] == 1


# -- retirement → snapshot + induction --------------------------------------
def test_retiree_retained_and_inducted():
    w = build_world(seed=5)
    p = next(iter(w.players.values()))
    p.career = _star_career()
    p.accolades = {"mvp": 3, "all_league": 7, "champion": 1}
    p.age = RETIREMENT_AGE                            # force retirement
    pid = p.pid
    result = offseason.age_and_retire(w)
    assert pid not in w.players                       # removed from the active pool
    assert any(s["pid"] == pid for s in w.retired)   # but retained as a snapshot
    assert any(s["pid"] == pid for s in w.hall_of_fame)
    assert any(s["pid"] == pid for s in result["inducted"])


# -- leaderboards -----------------------------------------------------------
def test_leaderboards_rank_living_and_retired():
    w = build_world(seed=6, backstory=False)        # no fabricated legends competing on the board
    living = next(iter(w.players.values()))
    living.career = _star_career(years=10, ppg=20.0)   # 15,000 pts
    w.retired.append({"pid": -1, "name": "Old Legend", "position": "SF", "seasons": 18,
                      "peak_ovr": 92, "last_team": "ZZZ", "first_year": 1990, "last_year": 2008,
                      "totals": {"pts": 31000, "reb": 9000, "ast": 6000, "gp": 1300},
                      "accolades": {"mvp": 4}, "hof": True})
    rows = legacy.leaderboards(w, "pts", limit=5)
    assert rows[0]["pid"] == -1                        # retired legend tops scoring
    assert rows[0]["active"] is False
    assert any(r["pid"] == living.pid and r["active"] for r in rows)


# -- full offseason integration ---------------------------------------------
def test_pre_draft_snapshots_retirees_and_returns_extras():
    w = _played_world(seed=3)
    champ_tid = P.champion(w)
    before = len(w.retired)
    summary = offseason.pre_draft(w, champ_tid)
    assert "inducted" in summary and "milestones" in summary
    assert len(w.retired) - before == summary["retired"]
    # the champion's surviving players picked up a championship accolade
    champ = w.teams[champ_tid]
    assert any(w.players[pid].accolades.get("champion", 0) >= 1
               for pid in champ.roster if pid in w.players)


# -- serialization ----------------------------------------------------------
def test_save_round_trip_preserves_legacy():
    w = build_world(seed=7)
    p = next(iter(w.players.values()))
    p.accolades = {"mvp": 1, "all_league": 3}
    w.hall_of_fame.append({"pid": 99, "name": "Test HoFer", "totals": {"pts": 25000}, "hof": True})
    w.retired.append({"pid": 99, "name": "Test HoFer", "totals": {"pts": 25000}, "hof": True})
    w2 = World.from_dict(w.to_dict())
    assert w2.hall_of_fame == w.hall_of_fame
    assert w2.retired == w.retired
    assert w2.players[p.pid].accolades == {"mvp": 1, "all_league": 3}
