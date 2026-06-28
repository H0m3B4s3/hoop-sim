"""Dead-cap (waive penalty) tests — see #6 in the pain-point triage."""
from __future__ import annotations

from hoopsim.config import VETERAN_MINIMUM
from hoopsim.gen.leaguegen import build_world
from hoopsim.models.contract import flat_contract
from hoopsim.models.team import dead_cap
from hoopsim.save.serialize import world_from_json, world_to_json
from hoopsim.systems import cap
from hoopsim.systems.offseason import expire_contracts


def _give_contract(world, team, annual, years):
    """Put a fresh, fully-guaranteed contract on one of the team's players; return the pid."""
    pid = team.roster[0]
    world.players[pid].contract = flat_contract(annual, years, world.season_year)
    return pid


def test_waiving_above_minimum_creates_dead_money():
    w = build_world(seed=1)
    team = w.teams[0]
    pid = _give_contract(w, team, 12_000_000, 3)        # $12M x 3, all guaranteed
    payroll_before = cap.payroll(w, team)
    w.release_player(pid)
    # The full guaranteed amount (36M) is stretched over 2*3+1 = 7 seasons.
    assert team.dead_money
    assert sum(team.dead_money) == 36_000_000
    assert len(team.dead_money) == 7
    # Dead money counts toward the cap this season.
    assert dead_cap(team) == team.dead_money[0]
    assert cap.payroll(w, team) == payroll_before - 12_000_000 + dead_cap(team)


def test_waiving_minimum_leaves_no_dead_money():
    w = build_world(seed=2)
    team = w.teams[0]
    pid = _give_contract(w, team, VETERAN_MINIMUM, 2)
    w.release_player(pid)
    assert dead_cap(team) == 0
    assert team.dead_money == []


def test_dead_money_schedule_stretch_and_exactness():
    # Odd totals must still sum exactly (remainder lands on the first season).
    c = flat_contract(10_000_001, 1, 2025)
    sched = build_world(seed=3).dead_money_schedule(c)
    assert len(sched) == 3                              # 2*1 + 1
    assert sum(sched) == 10_000_001
    # Minimum deals schedule nothing.
    assert build_world(seed=3).dead_money_schedule(flat_contract(VETERAN_MINIMUM, 2, 2025)) == []


def test_dead_money_decays_across_offseason():
    w = build_world(seed=4)
    team = w.teams[0]
    pid = _give_contract(w, team, 9_000_000, 2)         # 18M over 2*2+1 = 5 seasons
    w.release_player(pid)
    this_year = team.dead_money[0]
    total_before = sum(team.dead_money)
    expire_contracts(w)                                 # rolls the ledger forward one season
    assert sum(team.dead_money) == total_before - this_year
    assert len(team.dead_money) == 4


def test_dead_money_survives_save_round_trip():
    w = build_world(seed=6)
    team = w.teams[0]
    pid = _give_contract(w, team, 15_000_000, 2)
    w.release_player(pid)
    ledger = list(team.dead_money)
    assert ledger                                       # sanity: there is something to preserve
    w2 = world_from_json(world_to_json(w))
    assert w2.teams[team.tid].dead_money == ledger
