"""Prospect pre-draft stat generation and round-trip persistence."""
from __future__ import annotations

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.player import Player
from hoopsim.systems import draft_system as D


def test_every_prospect_has_a_plausible_stat_line():
    w = build_world(seed=3)
    w.user_team_id = 1
    ids = D.generate_draft_class(w)
    for pid in ids:
        s = w.players[pid].pre_draft
        assert s is not None
        assert {"level", "gp", "ppg", "rpg", "apg", "fg_pct", "tp_pct"} <= set(s)
        assert 2.0 <= s["ppg"] <= 35.0
        assert 0.18 <= s["tp_pct"] <= 0.50
        assert 0.34 <= s["fg_pct"] <= 0.68


def test_bigs_rebound_more_than_guards_on_average():
    w = build_world(seed=11)
    w.user_team_id = 1
    ids = D.generate_draft_class(w)
    bigs = [w.players[p].pre_draft["rpg"] for p in ids if w.players[p].position in ("PF", "C")]
    guards = [w.players[p].pre_draft["rpg"] for p in ids if w.players[p].position in ("PG", "SG")]
    assert sum(bigs) / len(bigs) > sum(guards) / len(guards)


def test_pre_draft_survives_serialization():
    w = build_world(seed=5)
    w.user_team_id = 1
    ids = D.generate_draft_class(w)
    p = w.players[ids[0]]
    clone = Player.from_dict(p.to_dict())
    assert clone.pre_draft == p.pre_draft


def test_non_prospects_have_no_pre_draft_line():
    w = build_world(seed=2)
    team = w.team_list()[0]
    assert all(w.players[pid].pre_draft is None for pid in team.roster)
