"""Fog-of-war potential grading."""
from __future__ import annotations

from hoopsim.gen.leaguegen import build_world
from hoopsim.systems import draft_system as D
from hoopsim.systems import scouting as SC


from hoopsim.models.world import World


def _prospect(seed=3):
    w = build_world(seed=seed)
    w.user_team_id = 1
    ids = D.generate_draft_class(w)
    return w.players[ids[0]]


def test_toggle_off_reveals_exact_number():
    p = _prospect()
    v = SC.pot_view(p, fog=False)
    assert v.known and v.low == v.high == v.value == p.scouted_potential()
    assert "–" not in SC.pot_band_str(p, fog=False)
    assert "–" in SC.pot_band_str(p, fog=True)          # fog back on → banded again


def test_fog_is_a_per_career_setting_that_survives_a_save():
    w = build_world(seed=3)
    assert SC.fog_enabled(w)                            # config default
    w.fog_of_war = False
    other = build_world(seed=3)
    assert not SC.fog_enabled(w) and SC.fog_enabled(other)
    assert not SC.fog_enabled(World.from_dict(w.to_dict()))
    d = other.to_dict()
    d.pop("fog_of_war")
    assert World.from_dict(d).fog_of_war is None        # older saves fall back to the default


def test_prospect_band_is_wide_and_hides_the_number():
    p = _prospect()
    v = SC.pot_view(p)
    assert not v.known
    assert v.high - v.low >= 6
    assert v.low >= p.overall and v.high <= 99
    assert "–" in SC.pot_band_str(p)          # banded, not a bare integer


def test_veteran_band_is_tight_and_known():
    w = build_world(seed=2)
    vet = next(p for p in w.players.values()
               if p.age >= 28 and p.experience >= 5 and p.team_id is not None)
    v = SC.pot_view(vet)
    assert v.known
    assert v.high - v.low <= 2


def test_grade_is_monotonic_in_value():
    grades = [SC.potential_grade(v) for v in range(60, 96)]
    order = ["D", "C-", "C", "C+", "B-", "B", "B+", "A-", "A", "A+"]
    seen = [g for g in grades]
    # Grades only ever climb as the value rises.
    idxs = [order.index(g) for g in seen]
    assert idxs == sorted(idxs)


def test_band_brackets_true_potential_most_of_the_time():
    """Over a class, the fogged band should usually contain the real ceiling."""
    w = build_world(seed=8)
    w.user_team_id = 1
    ids = D.generate_draft_class(w)
    hits = 0
    for pid in ids:
        p = w.players[pid]
        v = SC.pot_view(p)
        if v.low <= max(p.overall, min(99, p.potential)) <= v.high:
            hits += 1
    assert hits / len(ids) >= 0.85
