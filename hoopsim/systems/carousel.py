"""The coaching carousel: firing, hiring, and the market of available coaches and staff.

Before this, a coach was assigned once at world creation and stayed forever — an attribute, not a
decision. Now a bad season gets a coach fired, the fired coach lands back in a hiring pool with
his career record attached, and every offseason the league reshuffles. Career records travel with
the coach, so the pool is something you can actually read: a 480-390 retread is a different bet
from an unproven first-timer.

Expectations are relative to the rest of the league, not to a fixed win total, so a rebuilding
team is not fired for going 25-57 while a contender is not safe at 41-41. Tenure buys patience:
a coach in year one is rarely fired, and a long-serving coach with a good record has enough
credit to survive one bad year.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from hoopsim.models.coach import ARCHETYPES, Coach, apply_coach_tactics
from hoopsim.models.staff import LEVEL_SALARY, ROLE_KEYS, Assistant, staff_cost
from hoopsim.models.team import Team
from hoopsim.models.world import World

# -- firing -----------------------------------------------------------------
# Tuned so the league turns over ~5-7 benches a year and average tenure lands near 4 seasons,
# which is roughly the real rate. The credits below are deliberately capped and the whole result
# is floored: a coach who strings together good years should be hard to fire, never impossible.
GRACE_SEASONS = 1
# Anything under .500 starts generating real heat.
HOT_SEAT_WIN_PCT = 0.50
# Even a fine season carries some chance of a parting of ways (front-office churn).
BASE_FIRE_CHANCE = 0.06
# Scales how hard a bad record pushes toward a firing.
FIRE_SENSITIVITY = 3.0
MIN_FIRE_CHANCE = 0.02
MAX_FIRE_CHANCE = 0.85
# Credit earned by a long tenure and by a winning career, each capped so they cannot combine
# into permanent immunity.
TENURE_CREDIT = 0.03
MAX_TENURE_CREDIT = 0.10
WINNING_CREDIT = 0.10

# -- the market -------------------------------------------------------------
POOL_TARGET = 10          # coaches kept available for hire at any time
STAFF_POOL_TARGET = 16    # assistants available for hire

# The owner earmarks a slice of his budget for the bench behind the bench. Sized so a mid-market
# team can afford a couple of good specialists but not a full elite staff.
STAFF_BUDGET_DIVISOR = 20


def _expectation_gap(team: Team) -> float:
    """How far below a .500 baseline the team finished, as a win-percentage shortfall."""
    played = team.wins + team.losses
    if not played:
        return 0.0
    return max(0.0, HOT_SEAT_WIN_PCT - (team.wins / played))


def fire_chance(team: Team) -> float:
    """Probability this team parts with its head coach this offseason."""
    coach = team.coach
    if coach is None:
        return 0.0
    if coach.seasons < GRACE_SEASONS:
        return 0.0                       # you get one year before anyone judges you
    chance = BASE_FIRE_CHANCE + _expectation_gap(team) * FIRE_SENSITIVITY
    # A track record is worth something: every season past the second shaves the odds, and a
    # winning career record shaves them further. Both are capped, and the floor below means even
    # the best coach in the league is never entirely safe.
    chance -= min(MAX_TENURE_CREDIT, max(0, coach.seasons - 2) * TENURE_CREDIT)
    if coach.win_pct > 0.55:
        chance -= WINNING_CREDIT
    return max(MIN_FIRE_CHANCE, min(MAX_FIRE_CHANCE, chance))


# ---------------------------------------------------------------------------
# Market generation
# ---------------------------------------------------------------------------
def _names(rng):
    """A name source. The dedup set is per-instance and resets, which is fine here — a repeated
    surname across a decade of hires reads as normal, not as a bug."""
    from hoopsim.gen.namegen import NameGenerator
    return NameGenerator(rng)


def make_coach(rng) -> Coach:
    """A fresh, unproven coach for the hiring pool."""
    keys = list(ARCHETYPES.keys())
    weights = [ARCHETYPES[k].weight for k in keys]
    return Coach(name=f"Coach {_names(rng).name()[1]}", archetype=rng.weighted_one(keys, weights))


def make_assistant(rng, role: Optional[str] = None) -> Assistant:
    """A hireable assistant. Elite specialists are deliberately scarce."""
    first, last = _names(rng).name()
    role = role or rng.choice(list(ROLE_KEYS))
    level = rng.weighted_one([1, 2, 3, 4, 5], [30.0, 28.0, 22.0, 14.0, 6.0])
    return Assistant(name=f"{first} {last}", role=role, level=level)


def refill_market(world: World, rng=None) -> None:
    """Top the coach and assistant pools back up to their targets.

    ``rng`` defaults to ``world.rng``. World creation passes the separate salted coach stream
    instead, so seeding the market never perturbs the main sequence that builds rosters — the
    same isolation guarantee coach assignment itself relies on (see gen/CLAUDE.md).
    """
    rng = rng or world.rng
    while len(world.coach_pool) < POOL_TARGET:
        world.coach_pool.append(make_coach(rng))
    while len(world.staff_pool) < STAFF_POOL_TARGET:
        world.staff_pool.append(make_assistant(rng))


# ---------------------------------------------------------------------------
# Hiring / firing
# ---------------------------------------------------------------------------
def fire_coach(world: World, team: Team) -> Optional[Coach]:
    """Remove a team's head coach and return him to the market. Returns the fired coach."""
    coach = team.coach
    if coach is None:
        return None
    team.coach = None
    world.coach_pool.append(coach)
    return coach


def hire_coach(world: World, team: Team, coach: Coach) -> None:
    """Install a coach and re-seed the team's tactical identity from his archetype."""
    if coach in world.coach_pool:
        world.coach_pool.remove(coach)
    coach.hired_year = world.season_year
    team.coach = coach
    apply_coach_tactics(team)


def _coach_appeal(coach: Coach) -> float:
    """How attractive a candidate looks to an AI front office."""
    # An unproven coach is a coin flip, so he sits mid-pack rather than at the bottom — that is
    # what lets a first-timer occasionally beat out a retread with a losing record.
    if coach.seasons == 0:
        return 0.50
    return coach.win_pct + min(0.08, coach.seasons * 0.01)


def hire_best_available(world: World, team: Team) -> Optional[Coach]:
    """AI hiring: the better the team's own record, the better the coach it can attract."""
    if not world.coach_pool:
        refill_market(world)
    played = team.wins + team.losses
    standing = (team.wins / played) if played else 0.5
    ranked = sorted(world.coach_pool, key=_coach_appeal, reverse=True)
    # A 60-win team gets its pick; a 20-win team is choosing from further down the board.
    reach = max(1, int(len(ranked) * (1.0 - standing) * 0.8) + 1)
    pick = ranked[world.rng.randint(0, min(reach, len(ranked)) - 1)]
    hire_coach(world, team, pick)
    return pick


def hire_assistant(world: World, team: Team, assistant: Assistant) -> None:
    """Hire a specialist, replacing whoever held that slot (the incumbent returns to the pool)."""
    if assistant in world.staff_pool:
        world.staff_pool.remove(assistant)
    for existing in list(team.staff):
        if existing.role == assistant.role:
            team.staff.remove(existing)
            world.staff_pool.append(existing)
    team.staff.append(assistant)


def fire_assistant(world: World, team: Team, role: str) -> Optional[Assistant]:
    for existing in list(team.staff):
        if existing.role == role:
            team.staff.remove(existing)
            world.staff_pool.append(existing)
            return existing
    return None


def staff_budget_room(team: Team) -> int:
    """Owner money left for staff. Staff sits outside the salary cap, on its own budget line."""
    return max(0, team.owner_budget // STAFF_BUDGET_DIVISOR - staff_cost(team.staff))


def ai_build_staff(world: World, team: Team, rng=None) -> None:
    """Fill a team's open staff slots with whatever its budget affords.

    Every team ends up with a full bench of assistants where budget allows — real staffs differ
    in *quality*, not in whether they exist. So when the market has nobody left for a role, a new
    candidate is generated for it rather than leaving the slot empty; otherwise whichever team
    happened to hire first would drain the pool and everyone after it would field nobody.
    """
    rng = rng or world.rng
    for role in ROLE_KEYS:
        if any(a.role == role for a in team.staff):
            continue
        room = staff_budget_room(team)
        options = [a for a in world.staff_pool if a.role == role and a.salary <= room]
        if not options:
            candidate = make_assistant(rng, role)
            if candidate.salary > room:
                continue                  # genuinely cannot afford this slot
            world.staff_pool.append(candidate)
            options = [candidate]
        # Richer teams reach for the best specialist available; poorer ones take what fits.
        options.sort(key=lambda a: a.level, reverse=True)
        if rng.chance(0.65):
            hire_assistant(world, team, options[0])
        else:
            hire_assistant(world, team, rng.choice(options))


# ---------------------------------------------------------------------------
# The offseason step
# ---------------------------------------------------------------------------
def record_coach_season(world: World) -> None:
    """Roll each team's finished season into its coach's career record."""
    for team in world.team_list():
        if team.coach is not None:
            team.coach.wins += team.wins
            team.coach.losses += team.losses
            team.coach.seasons += 1


def run_carousel(world: World) -> dict:
    """Fire, then hire, across the league. The user's team is never touched automatically.

    Returns a summary of what moved, so the caller can report it.
    """
    fired: List[dict] = []
    hired: List[dict] = []
    refill_market(world)
    for team in world.team_list():
        if team.tid == world.user_team_id:
            continue                      # the user makes his own call on his own bench
        if team.coach is not None and world.rng.chance(fire_chance(team)):
            coach = fire_coach(world, team)
            if coach is not None:
                fired.append({"tid": team.tid, "team": team.full_name, "coach": coach.name,
                              "record": f"{team.wins}-{team.losses}",
                              "seasons": coach.seasons})
    # Vacancies fill after every firing resolves, so a fired coach can land another job the
    # same offseason — which is what actually makes it read like a carousel.
    for team in world.team_list():
        if team.coach is None and team.tid != world.user_team_id:
            coach = hire_best_available(world, team)
            if coach is not None:
                hired.append({"tid": team.tid, "team": team.full_name, "coach": coach.name,
                              "record": coach.record_str, "seasons": coach.seasons})
        if team.tid != world.user_team_id:
            ai_build_staff(world, team)
    refill_market(world)
    return {"fired": fired, "hired": hired}
