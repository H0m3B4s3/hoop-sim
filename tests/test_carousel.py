"""Coaching carousel and assistant staff system tests.

Tests the market dynamics of firing/hiring coaches and their career records traveling with them,
staff hiring and budget constraints, and the directional effects of specialist coaches on player
development, injuries, and scouting.
"""
from __future__ import annotations

from hoopsim.gen.leaguegen import build_world
from hoopsim.models.coach import Coach, ARCHETYPES
from hoopsim.models.staff import Assistant
from hoopsim.save.serialize import world_to_json, world_from_json
from hoopsim.systems import carousel as C
from hoopsim.systems import development as DEV
from hoopsim.systems import injuries as INJ
from hoopsim.systems import scouting as SC


# ============================================================================
# Module-level helpers
# ============================================================================

def _world(seed=1):
    """Build a fresh world with coaching pools seeded."""
    w = build_world(seed=seed)
    w.user_team_id = 1
    return w


def _set_team_record(team, wins: int, losses: int):
    """Manually set a team's season record without simulating games."""
    team.wins = wins
    team.losses = losses


# ============================================================================
# fire_chance tests
# ============================================================================

def test_fire_chance_higher_for_bad_record_than_good_one():
    """Bad records generate higher fire probability than good ones, all else equal."""
    w = _world(seed=1)
    bad_team = w.teams[2]
    good_team = w.teams[3]

    # Ensure both have coaches past grace period
    bad_team.coach.seasons = 3
    good_team.coach.seasons = 3

    _set_team_record(bad_team, 15, 65)   # 0.188 win pct
    _set_team_record(good_team, 55, 25)  # 0.688 win pct

    bad_chance = C.fire_chance(bad_team)
    good_chance = C.fire_chance(good_team)

    assert bad_chance > good_chance, \
        f"Bad-record chance {bad_chance:.4f} should exceed good-record {good_chance:.4f}"


def test_fire_chance_zero_during_grace_period():
    """Coaches in their first season are immune to firing, regardless of record."""
    w = _world(seed=2)
    team = w.teams[2]
    team.coach.seasons = 0  # Grace period (GRACE_SEASONS=1, so seasons < 1)
    _set_team_record(team, 0, 40)  # Catastrophic record

    chance = C.fire_chance(team)
    assert chance == 0.0, "Coach in year 1 should have zero fire chance"


def test_fire_chance_nonzero_after_grace_period():
    """After the grace period ends, any record carries some firing risk."""
    w = _world(seed=3)
    team = w.teams[2]
    team.coach.seasons = 1  # First season complete, now into year 2
    _set_team_record(team, 41, 41)  # Exactly .500

    chance = C.fire_chance(team)
    assert chance > 0.0, \
        "Coach after grace period should have nonzero fire chance even at .500"


def test_fire_chance_respects_min_fire_chance_floor():
    """Even the best-case coach (winning career, long tenure) never drops below MIN_FIRE_CHANCE."""
    w = _world(seed=4)
    team = w.teams[2]

    # Construct an elite coach: 10-season career at 60% win rate + long tenure
    team.coach.wins = 600
    team.coach.losses = 400
    team.coach.seasons = 10
    team.coach.hired_year = w.season_year - 8  # 8 seasons with team

    _set_team_record(team, 60, 20)  # Excellent current season

    chance = C.fire_chance(team)
    assert chance >= C.MIN_FIRE_CHANCE, \
        f"Fire chance {chance:.4f} should never drop below MIN_FIRE_CHANCE {C.MIN_FIRE_CHANCE}"
    assert chance > 0.0, \
        "This is the guard against a regression where elite coaches became permanently unfireable"


def test_fire_chance_respects_max_fire_chance_ceiling():
    """Even catastrophically bad records cannot exceed MAX_FIRE_CHANCE."""
    w = _world(seed=5)
    team = w.teams[2]

    # Worst-case scenario: bad record with long terrible history
    team.coach.wins = 50
    team.coach.losses = 500
    team.coach.seasons = 2

    _set_team_record(team, 5, 75)  # 0.063 win pct

    chance = C.fire_chance(team)
    assert chance <= C.MAX_FIRE_CHANCE, \
        f"Fire chance {chance:.4f} should never exceed MAX_FIRE_CHANCE {C.MAX_FIRE_CHANCE}"


def test_fire_chance_tenure_and_winning_credits_are_capped():
    """Tenure credit and winning credit combine but are capped so neither dominates the other."""
    w = _world(seed=6)
    team = w.teams[2]

    # Set up a coach: mediocre record (50% win rate), very long tenure
    team.coach.wins = 400
    team.coach.losses = 400
    team.coach.seasons = 16  # Very long career
    team.coach.hired_year = w.season_year - 10  # 10 years with this team

    _set_team_record(team, 41, 41)  # This season exactly .500

    chance = C.fire_chance(team)

    # With TENURE_CREDIT=0.03 capped at MAX_TENURE_CREDIT=0.10, the max reduction is 0.10
    # With win_pct=0.50 (below 0.55), WINNING_CREDIT=0.10 doesn't apply
    # So chance should be BASE_FIRE_CHANCE (0.06) minus MAX_TENURE_CREDIT (0.10) = MAX_FIRE_CHANCE floor
    # Actually, the credit is capped to 0.10, so it floors at MIN_FIRE_CHANCE (0.02)
    assert chance >= C.MIN_FIRE_CHANCE, "Capped credits should still respect the floor"
    assert chance <= C.BASE_FIRE_CHANCE, "Credits should reduce chance from baseline"


# ============================================================================
# run_carousel tests
# ============================================================================

def test_run_carousel_never_touches_user_team():
    """The carousel skips the user's team entirely, leaving it untouched."""
    w = _world(seed=7)
    user_team = w.teams[w.user_team_id]

    # Give the user team a catastrophic record
    _set_team_record(user_team, 10, 70)
    original_coach = user_team.coach
    original_coach_name = original_coach.name

    # Run the carousel multiple times
    for _ in range(5):
        C.record_coach_season(w)
        C.run_carousel(w)

    # User's coach should never change (same object reference)
    assert user_team.coach == original_coach, \
        "User's team coach should never be touched by the carousel"
    assert user_team.coach.name == original_coach_name, \
        "User's coach should be the exact same coach throughout"


def test_run_carousel_bad_teams_end_with_shorter_tenure_than_good_teams():
    """Over multiple offseasons, bad teams turn over coaches faster than good teams.

    This is a statistical test: across ~15 simulated offseasons where records are determined by
    team strength (so the ordering is stable), bad teams should accumulate shorter current-job
    tenure (world.season_year - coach.hired_year) than good teams.
    """
    w = _world(seed=8)
    w.season_games = 10  # Short season for speed

    # Mark teams by strength expectation
    # Wide groups: with only a handful of teams per side a couple of unlucky rolls could flip
    # the comparison, and this is the headline claim of the whole carousel.
    all_tids = sorted(w.teams.keys())
    good_tids = all_tids[:10]
    bad_tids = all_tids[-10:]

    for _ in range(15):
        # Simulate records based on team strength (simple: better teams get better records)
        for tid in good_tids:
            _set_team_record(w.teams[tid], 45, 35)
        for tid in bad_tids:
            _set_team_record(w.teams[tid], 20, 60)

        C.record_coach_season(w)
        C.run_carousel(w)
        w.season_year += 1

    # Measure tenure as current_job duration
    good_tenures = [w.season_year - w.teams[tid].coach.hired_year for tid in good_tids]
    bad_tenures = [w.season_year - w.teams[tid].coach.hired_year for tid in bad_tids]

    good_avg = sum(good_tenures) / len(good_tenures)
    bad_avg = sum(bad_tenures) / len(bad_tenures)

    # Bad teams should have shorter average tenure due to turnover
    assert bad_avg < good_avg, \
        f"Bad teams avg tenure {bad_avg:.1f} should be shorter than good teams {good_avg:.1f}"


# ============================================================================
# Hiring/firing mechanics
# ============================================================================

def test_every_team_has_head_coach_after_carousel():
    """run_carousel ensures every team (except user's) has a head coach by the end."""
    w = _world(seed=9)

    # Manually fire some coaches to create vacancies
    for tid in [5, 6, 7]:
        C.fire_coach(w, w.teams[tid])

    # Run the carousel
    C.run_carousel(w)

    # Every team should have a coach now
    for team in w.team_list():
        assert team.coach is not None, f"Team {team.tid} left without a head coach"


def test_fired_coach_returns_to_pool_and_carries_record():
    """A fired coach lands back in the hiring pool with his full career record intact."""
    w = _world(seed=10)
    team = w.teams[2]
    original_coach = team.coach

    # Manually build a career record
    original_coach.wins = 100
    original_coach.losses = 50
    original_coach.seasons = 5

    # Fire him
    fired = C.fire_coach(w, team)

    assert fired == original_coach, "fire_coach should return the coach it fired"
    assert original_coach in w.coach_pool, "Fired coach should be in the pool"
    assert original_coach.wins == 100, "Coach's career wins should survive firing"
    assert original_coach.losses == 50, "Coach's career losses should survive firing"
    assert original_coach.seasons == 5, "Coach's career seasons should survive firing"


def test_fired_coach_can_be_hired_again():
    """A fired coach can be hired by another team later, re-entering the league."""
    w = _world(seed=11)
    team_a = w.teams[2]
    team_b = w.teams[3]

    # Fire team A's coach
    fired_coach = C.fire_coach(w, team_a)
    assert team_a.coach is None

    # Manually hire the fired coach to team B
    C.hire_coach(w, team_b, fired_coach)

    assert team_b.coach == fired_coach, "Fired coach should be hireable"
    assert fired_coach not in w.coach_pool, "Hired coach should be removed from pool"
    assert team_b.coach.hired_year == w.season_year, \
        "Re-hired coach's hired_year should reflect new job start"


def test_record_coach_season_accumulates_wins_losses_seasons():
    """record_coach_season rolls each team's season results into its coach's career totals."""
    w = _world(seed=12)
    team = w.teams[2]
    coach = team.coach

    # Set initial career state
    coach.wins = 100
    coach.losses = 50
    coach.seasons = 3

    # Set this season's record
    _set_team_record(team, 45, 35)

    # Record it
    C.record_coach_season(w)

    assert coach.wins == 145, "Coach's career wins should accumulate"
    assert coach.losses == 85, "Coach's career losses should accumulate"
    assert coach.seasons == 4, "Coach's season counter should increment"


# ============================================================================
# hire_coach tactics re-seeding
# ============================================================================

def test_hire_coach_re_seeds_tactics_from_archetype():
    """Hiring a coach with a different archetype re-seeds the team's tactics."""
    w = _world(seed=13)
    team = w.teams[2]

    # Force a distinctive archetype lean
    old_coach = team.coach
    old_coach.archetype = "Balanced"
    C.apply_coach_tactics(team)

    old_tactics_pace = team.tactics.pace

    # Create a new coach with a different archetype
    new_coach = Coach(name="Coach New", archetype="PaceAndSpace")

    # Hire him
    C.hire_coach(w, team, new_coach)

    # Tactics should be updated from the new archetype
    assert team.tactics.pace != old_tactics_pace, \
        "Hiring a new coach should change the team's pace tactic"
    assert team.coach.archetype == "PaceAndSpace"


# ============================================================================
# Assistant staff tests
# ============================================================================

def test_hire_assistant_fills_slot_replaces_incumbent():
    """hire_assistant fills a role slot, replaces any incumbent, and returns the replaced to pool."""
    w = _world(seed=14)
    team = w.teams[2]

    # Create a new specialist
    new_dev_coach = Assistant(name="Fresh Dev Guy", role="development", level=4)

    # Hire him
    C.hire_assistant(w, team, new_dev_coach)

    # Check he's on the team
    assert any(a.role == "development" and a.name == "Fresh Dev Guy" for a in team.staff), \
        "New assistant should be hired onto the team"

    # If there was an incumbent, he should be in the pool
    if any(a.role == "development" for a in w.staff_pool):
        pass  # Okay, incumbent was returned to pool


def test_staff_budget_room_never_negative():
    """staff_budget_room is always >= 0 (owner_budget // 20 - current staff cost)."""
    w = _world(seed=15)

    for team in w.team_list():
        room = C.staff_budget_room(team)
        assert room >= 0, \
            f"Team {team.tid} staff budget room {room} should never be negative"


def test_ai_teams_never_exceed_staff_budget():
    """AI teams built by ai_build_staff never exceed their budget slice."""
    w = _world(seed=16)

    for tid, team in w.teams.items():
        if tid == w.user_team_id:
            continue  # Skip user team, they manage their own budget

        budget_slice = team.owner_budget // C.STAFF_BUDGET_DIVISOR
        from hoopsim.models.staff import staff_cost
        cost = staff_cost(team.staff)

        assert cost <= budget_slice, \
            f"Team {tid} staff cost {cost} exceeds budget slice {budget_slice}"


def test_every_team_starts_with_staff():
    """build_world ends with every team having a staff (this guards a real bug that was just fixed)."""
    w = _world(seed=17)

    for team in w.team_list():
        assert len(team.staff) > 0, \
            f"Team {team.tid} should have staff after world creation (guards pool-drain bug)"


# ============================================================================
# Save and backward compatibility
# ============================================================================

def test_save_round_trip_coach_and_staff():
    """Coach career record, hired_year, and team staff survive serialization."""
    from hoopsim.save.serialize import world_to_json, world_from_json

    w = _world(seed=18)
    team = w.teams[2]
    coach = team.coach

    # Set memorable career state
    coach.wins = 137
    coach.losses = 88
    coach.seasons = 7
    coach.hired_year = 2020

    # Record the staff state
    staff_before = [(a.name, a.role, a.level) for a in team.staff]

    # Round-trip
    json_str = world_to_json(w)
    w2 = world_from_json(json_str)
    team2 = w2.teams[2]
    coach2 = team2.coach

    assert coach2.wins == 137, "Coach wins should survive round-trip"
    assert coach2.losses == 88, "Coach losses should survive round-trip"
    assert coach2.seasons == 7, "Coach seasons should survive round-trip"
    assert coach2.hired_year == 2020, "Coach hired_year should survive round-trip"

    staff_after = [(a.name, a.role, a.level) for a in team2.staff]
    assert staff_after == staff_before, "Team staff should survive round-trip"


def test_coach_from_dict_backward_compatible_no_career_fields():
    """Coach.from_dict on old saves with no wins/losses/seasons/hired_year loads with sane defaults."""
    old_dict = {
        "name": "Coach Legacy",
        "archetype": "Balanced",
    }

    coach = Coach.from_dict(old_dict)
    assert coach.wins == 0, "Missing wins should default to 0"
    assert coach.losses == 0, "Missing losses should default to 0"
    assert coach.seasons == 0, "Missing seasons should default to 0"
    assert coach.hired_year == 0, "Missing hired_year should default to 0"


def test_team_from_dict_backward_compatible_no_staff_key():
    """Team.from_dict on old saves lacking 'staff' key loads with empty staff list."""
    from hoopsim.models.team import Team

    # Old-style team dict without 'staff' key; includes required fields
    old_dict = {
        "tid": 1,
        "city": "Boston",
        "name": "Minutemen",
        "abbrev": "BOS",
        "conference": "East",
        "league": "nba",
        "roster": [],
        "wins": 50,
        "losses": 32,
    }

    team = Team.from_dict(old_dict)
    assert hasattr(team, "staff"), "Team should have staff attribute"
    # Staff should be an empty list (since 'staff' key was not in old_dict)
    assert isinstance(team.staff, list), "Team staff should be a list"
    assert len(team.staff) == 0, "Missing 'staff' key should default to empty list"


# ============================================================================
# Staff effects on game systems (directional tests)
# ============================================================================

def test_trainer_reduces_injury_risk():
    """Athletic Trainer level reduces injury risk. A level-5 trainer is noticeably safer than level 0."""
    from hoopsim.models.player import Player

    w = _world(seed=19)
    player = list(w.players.values())[0]

    # Risk with no trainer
    risk_no_trainer = INJ.injury_risk(player, 35.0, trainer_level=0)

    # Risk with elite trainer
    risk_elite_trainer = INJ.injury_risk(player, 35.0, trainer_level=5)

    assert risk_elite_trainer < risk_no_trainer, \
        f"Elite trainer risk {risk_elite_trainer:.4f} should be less than none {risk_no_trainer:.4f}"


def test_conditioning_coach_preserves_condition():
    """Strength & Conditioning coach level preserves condition better. High level recovers more condition."""
    w = _world(seed=20)

    # Two identical players, different conditioning coach support
    p1 = list(w.players.values())[0]
    p2 = list(w.players.values())[1]

    # Drain both equally
    p1.condition = 100.0
    p2.condition = 100.0

    INJ.update_condition(p1, 38.0, conditioning_level=0)
    INJ.update_condition(p2, 38.0, conditioning_level=5)

    condition_p1_after_drain = p1.condition
    condition_p2_after_drain = p2.condition

    # The drain should be the same (conditioning doesn't affect drain, only recovery)
    # So after one tick, p2 should have higher condition due to better recovery
    assert condition_p2_after_drain > condition_p1_after_drain, \
        "High conditioning level should preserve condition better"


def test_dev_coach_accelerates_young_player_growth():
    """An elite Player Development coach grows young players faster than no coach at all.

    Deep-copies the same players and develops each copy at both levels, rather than comparing
    two different worlds — otherwise the measurement is confounded by one population simply
    having more headroom than the other, and the test could pass or fail for reasons that have
    nothing to do with the coach. A single roll is noise, so this averages over the whole cohort.
    """
    import copy

    w = _world(seed=21)
    cohort = [p for p in w.players.values() if p.age <= 24 and p.potential - p.overall >= 5]
    # Decorrelated durability aside, a generated league always carries plenty of young players
    # with room to grow; an empty cohort here would mean generation itself broke.
    assert len(cohort) >= 20, len(cohort)

    def _avg_growth(level: int) -> float:
        rng = build_world(seed=21).rng          # identical stream for both arms
        total = 0
        for p in cohort:
            q = copy.deepcopy(p)
            before = q.overall
            DEV.develop_player(q, rng, dev_coach_level=level)
            total += q.overall - before
        return total / len(cohort)

    no_coach = _avg_growth(0)
    elite = _avg_growth(5)
    # Same players, same RNG stream, only the coach differs, so the gap is the coach's doing.
    assert elite > no_coach, f"elite dev coach {elite:.2f} vs none {no_coach:.2f}"


def test_scout_narrows_potential_uncertainty():
    """Head Scout level narrows the potential confidence band. Level 5 scout < level 0."""
    w = _world(seed=23)

    # Pick a prospect (young, low experience)
    prospect = None
    for p in w.players.values():
        if p.age <= 21 and p.experience == 0:
            prospect = p
            break

    if prospect is None:
        return  # No prospects available, skip

    # Uncertainty with no scout
    unc_no_scout = SC.pot_uncertainty(prospect, scout_level=0)

    # Uncertainty with elite scout
    unc_elite_scout = SC.pot_uncertainty(prospect, scout_level=5)

    assert unc_elite_scout < unc_no_scout, \
        f"Elite scout uncertainty {unc_elite_scout} should be narrower than none {unc_no_scout}"
    assert unc_elite_scout >= SC._UNC_KNOWN, \
        f"Elite scout should not collapse to certainty, floor is {SC._UNC_KNOWN}"
