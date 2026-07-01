"""Chemistry (lineup familiarity): accrual, persistence, departures, and seeding."""
from __future__ import annotations

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.team import (lineup_familiarity_secs, pair_key, seed_chemistry)
from hoopsim.sim.engine import simulate_game
from hoopsim.sim.ratings import CHEM_R_MIN, FULL_CHEM_SECS, familiarity_realization


def test_pair_key_order_independent():
    assert pair_key(3, 7) == pair_key(7, 3) == "3,7"


def test_familiarity_realization_bounds():
    assert familiarity_realization(0.0) == CHEM_R_MIN          # strangers
    assert familiarity_realization(FULL_CHEM_SECS) == 1.0      # fully gelled
    assert familiarity_realization(FULL_CHEM_SECS * 5) == 1.0  # saturates, never exceeds 1.0
    lo = familiarity_realization(FULL_CHEM_SECS * 0.25)
    assert CHEM_R_MIN < lo < 1.0                                # monotonic in between


def test_fresh_world_is_gelled():
    # Seeded at world creation -> an established roster reads as full chemistry from tip-off.
    w = build_world(seed=5)
    team = next(iter(w.teams.values()))
    secs = lineup_familiarity_secs(team.chemistry, team.starters[:5])
    assert familiarity_realization(secs) == 1.0


def test_new_pairing_starts_cold():
    w = build_world(seed=5)
    team = next(iter(w.teams.values()))
    # A five that has never shared the floor (no pair history) sits at the floor.
    strangers = [10_001, 10_002, 10_003, 10_004, 10_005]
    secs = lineup_familiarity_secs({}, strangers)
    assert familiarity_realization(secs) == CHEM_R_MIN


def test_chemistry_accrues_during_a_game():
    w = build_world(seed=5)
    teams = list(w.teams.values())
    h, a = teams[0], teams[1]
    # Wipe the seeded history so accrual is visible from zero.
    h.chemistry.clear()
    a.chemistry.clear()
    simulate_game(w, h, a)
    assert h.chemistry, "home team should have banked shared-floor time"
    # The starters who logged the most minutes together should top the table.
    top = max(h.chemistry.values())
    assert top > 0


def test_departure_clears_chemistry():
    w = build_world(seed=5)
    team = next(iter(w.teams.values()))
    pid = team.roster[0]
    seed_chemistry(team, FULL_CHEM_SECS)
    assert any(pid in (int(x) for x in k.split(",")) for k in team.chemistry)
    team.remove_player(pid)
    assert all(pid not in (int(x) for x in k.split(",")) for k in team.chemistry)


def test_chemistry_persists_through_serialization():
    from hoopsim.models.team import Team
    w = build_world(seed=5)
    team = next(iter(w.teams.values()))
    team.chemistry[pair_key(1, 2)] = 1234.5
    restored = Team.from_dict(team.to_dict())
    assert restored.chemistry[pair_key(1, 2)] == 1234.5
