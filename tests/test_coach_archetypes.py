"""Head-coach archetypes: rotation shaping, generation, and position-aware lineups."""
from __future__ import annotations

from collections import Counter

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.coach import (ARCHETYPES, BALANCED, Coach, apply_coach_tactics, assign_coach,
                                   profile_for)
from hoopsim.models.team import set_auto_minutes
from hoopsim.rng import Rng
from hoopsim.sim.engine import GameSim


def _team(seed=1):
    w = build_world(seed=seed)
    return w, w.teams[0]


# --- anchor: Balanced reproduces the historical (coachless) behavior --------
def test_balanced_matches_no_coach():
    w, team = _team()
    team.coach = None
    set_auto_minutes(team, w.players)
    baseline = dict(team.minutes_target)

    team.coach = Coach(name="Coach Anchor", archetype="Balanced")
    set_auto_minutes(team, w.players)
    assert team.minutes_target == baseline


def test_unknown_archetype_falls_back_to_balanced():
    team = _team()[1]
    team.coach = Coach(archetype="NotARealCoach")
    assert team.coach.profile is BALANCED
    assert profile_for(team) is BALANCED


# --- rotation shaping: short vs deep ---------------------------------------
def test_iron_rotation_is_shorter_and_heavier_than_deep_bench():
    w, team = _team(seed=3)

    team.coach = Coach(archetype="IronRotation")
    set_auto_minutes(team, w.players)
    iron = dict(team.minutes_target)

    team.coach = Coach(archetype="DeepBench")
    set_auto_minutes(team, w.players)
    deep = dict(team.minutes_target)

    iron_players = sum(1 for m in iron.values() if m > 0)
    deep_players = sum(1 for m in deep.values() if m > 0)
    assert iron_players < deep_players                      # shorter bench
    assert max(iron.values()) > max(deep.values())          # rides starters harder
    assert max(iron.values()) >= 40                          # 44-min slack -> heavy starter minutes
    # both rotations still divide the standard 240 player-minutes
    assert sum(iron.values()) == sum(deep.values()) == 240


def test_star_reliance_concentrates_top_minutes():
    w, team = _team(seed=8)
    top = max(team.starters, key=lambda pid: w.players[pid].overall)

    team.coach = Coach(archetype="MotionEgalitarian")     # star_reliance 1.15 (flat)
    set_auto_minutes(team, w.players)
    flat = team.minutes_target[top]

    team.coach = Coach(archetype="IronRotation")          # star_reliance 1.70 (steep)
    set_auto_minutes(team, w.players)
    steep = team.minutes_target[top]
    assert steep > flat


# --- default tactics from the archetype lean -------------------------------
def test_apply_coach_tactics_sets_lean():
    team = _team()[1]
    team.coach = Coach(archetype="SevenSeconds")
    apply_coach_tactics(team)
    assert team.tactics.pace == "Fast"
    assert team.tactics.off_focus == "Perimeter"
    assert team.tactics.ball_movement == "Motion"


# --- generation: every team gets a coach; outliers stay rare ---------------
def test_generation_assigns_coaches():
    w = build_world(seed=7)
    for team in w.teams.values():
        assert team.coach is not None
        assert team.coach.archetype in ARCHETYPES


def test_assign_coach_is_varied_and_outliers_rare():
    rng = Rng(42)
    picks = Counter(assign_coach(rng, "X").archetype for _ in range(4000))
    assert len(picks) >= 5                                   # real variety
    outliers = {"SevenSeconds", "IronRotation", "MotionEgalitarian", "DeepBench"}
    outlier_share = sum(picks[k] for k in outliers) / sum(picks.values())
    assert outlier_share < 0.45                              # outliers are the minority
    assert picks["Balanced"] == max(picks.values())          # Balanced is most common


# --- serialization ----------------------------------------------------------
def test_coach_round_trips():
    c = Coach(name="Coach Stone", archetype="GrindItOut")
    assert Coach.from_dict(c.to_dict()) == c


def test_team_round_trip_preserves_coach():
    from hoopsim.models.team import Team
    w, team = _team()
    team.coach = Coach(name="Coach Vee", archetype="DefensiveAnchor")
    restored = Team.from_dict(team.to_dict())
    assert restored.coach == team.coach


def test_legacy_save_without_coach_loads():
    from hoopsim.models.team import Team
    team = _team()[1]
    d = team.to_dict()
    d.pop("coach", None)                                     # pre-coach save
    restored = Team.from_dict(d)
    assert restored.coach is None
    assert profile_for(restored) is BALANCED


# --- engine: soft positional balance ---------------------------------------
def test_choose_lineup_avoids_all_guard_lineup():
    w = build_world(seed=5)
    h, a = w.teams[0], w.teams[1]
    sim = GameSim(w, h, a)
    st = sim.home
    avail = list(st.available)
    assert len(avail) >= 7

    # Force a guard-heavy pool: everyone a PG except two designated centers.
    for pid in avail:
        st.players[pid].position = "PG"
        st.players[pid].secondary_position = None
    centers = avail[:2]
    for pid in centers:
        st.players[pid].position = "C"
    # Neutralize minutes/fatigue/fouls so position fit is what drives slotting.
    for pid in avail:
        st.target_secs[pid] = 1500.0
        st.secs_played[pid] = 0.0
        st.fatigue[pid] = 0.0
        st.fouls[pid] = 0

    st.choose_lineup(0.0)
    assert len(st.on_court) == 5
    assert all(c in st.on_court for c in centers)           # bigs slotted despite a guard glut


def test_choose_lineup_real_roster_is_positionally_sensible():
    w = build_world(seed=2)
    sim = GameSim(w, w.teams[0], w.teams[1])
    sim.home.choose_lineup(0.0)
    positions = [sim.home.players[pid].position for pid in sim.home.on_court]
    # a real five should never be all-backcourt or all-frontcourt
    assert any(p in ("PG", "SG") for p in positions)
    assert any(p in ("PF", "C") for p in positions)
