"""World generation — build a full league of teams, rosters, contracts, and free agents."""
from __future__ import annotations

import json
import os
import random
from typing import List

from hoopsim.config import (DEFAULT_SEASON_PRESET, ROOKIE_AGE_RANGE, SALARY_CAP, SEASON_PRESETS,
                          VETERAN_MINIMUM)
from hoopsim.gen.namegen import NameGenerator
from hoopsim.gen.playergen import _POSITION_WEIGHTS, make_player
from hoopsim.models.attributes import POSITIONS
from hoopsim.models.coach import apply_coach_tactics, assign_coach
from hoopsim.models.contract import flat_contract
from hoopsim.models.league import Phase
from hoopsim.models.player import Player
from hoopsim.models.team import Team, auto_set_lineup
from hoopsim.models.world import World
from hoopsim.rng import Rng

_TEAMS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "teams.json")

# Talent curve: target overall per roster slot (best -> worst) for a 14-man roster.
_ROSTER_CURVE = [86, 81, 78, 75, 73, 71, 69, 67, 65, 63, 61, 60, 58, 57]
_NUM_FREE_AGENTS = 70

# Light roster-building guardrails: every team carries at least this many of each primary
# position so rosters stay playable and never end up lopsided (e.g. all forwards). Remaining
# slots are filled by the league-wide weights, leaving room for noise and GM "identity".
_POSITION_MIN = {"PG": 2, "SG": 2, "SF": 2, "PF": 2, "C": 2}


def _roster_positions(rng: Rng, n: int) -> List[str]:
    """Assign a primary position to each of ``n`` roster slots with minimum coverage.

    Positions are shuffled across the talent curve so a team's best players aren't all
    forced into the same spot, while team strength noise still produces guard- or big-heavy
    rosters around the floor.
    """
    slots: List[str] = []
    for pos, lo in _POSITION_MIN.items():
        slots.extend([pos] * lo)
    weights = [_POSITION_WEIGHTS[p] for p in POSITIONS]
    while len(slots) < n:
        slots.append(rng.weighted_one(POSITIONS, weights))
    rng.shuffle(slots)
    return slots[:n]


def _load_team_records() -> List[dict]:
    with open(_TEAMS_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def salary_for(ovr: int, rng: Rng) -> int:
    """A believable salary for a player of a given overall, with noise."""
    if ovr >= 85:
        base = 25_000_000 + (ovr - 85) * 2_200_000
    elif ovr >= 80:
        base = 16_000_000 + (ovr - 80) * 1_800_000
    elif ovr >= 76:
        base = 9_000_000 + (ovr - 76) * 1_600_000
    elif ovr >= 72:
        base = 4_500_000 + (ovr - 72) * 1_000_000
    elif ovr >= 68:
        base = 2_500_000 + (ovr - 68) * 500_000
    else:
        base = VETERAN_MINIMUM
    base *= rng.uniform(0.85, 1.15)
    return max(VETERAN_MINIMUM, int(round(base / 100_000) * 100_000))


def _unique_jersey(rng: Rng, used: set) -> int:
    for _ in range(40):
        n = rng.randint(0, 55)
        if n not in used:
            used.add(n)
            return n
    n = max(used) + 1 if used else 0
    used.add(n)
    return n


def _build_roster(world: World, team: Team, names: NameGenerator) -> None:
    rng = world.rng
    team_strength = rng.gauss(0.0, 2.8)
    used_jerseys: set = set()
    players: List[Player] = []
    positions = _roster_positions(rng, len(_ROSTER_CURVE))

    for slot, base in enumerate(_ROSTER_CURVE):
        noise = rng.gauss(0.0, 2.5)
        star_bonus = rng.uniform(-2.0, 6.0) if slot == 0 else 0.0
        target = int(max(50, min(95, round(base + team_strength + noise + star_bonus))))
        p = make_player(world.rng, world.new_pid(), names,
                        position=positions[slot], target_overall=target)
        p.team_id = team.tid
        p.jersey = _unique_jersey(rng, used_jerseys)
        players.append(p)
        world.add_player(p)
        team.add_player(p.pid)

    _assign_contracts(world, team, players)
    auto_set_lineup(team, world.players)


def _assign_contracts(world: World, team: Team, players: List[Player]) -> None:
    rng = world.rng
    raw = [salary_for(p.overall, rng) for p in players]
    # Scale the payroll to a believable team target, holding minimum deals at the floor.
    target_payroll = SALARY_CAP * rng.uniform(0.82, 1.16)
    floor_total = sum(s for s in raw if s <= VETERAN_MINIMUM)
    flexible_total = sum(s for s in raw if s > VETERAN_MINIMUM)
    scale = ((target_payroll - floor_total) / flexible_total) if flexible_total else 1.0
    scale = max(0.5, min(1.6, scale))

    for p, base_salary in zip(players, raw):
        salary = (base_salary if base_salary <= VETERAN_MINIMUM
                  else max(VETERAN_MINIMUM, int(round(base_salary * scale / 100_000) * 100_000)))
        years = rng.randint(1, 4)
        signed_offset = rng.randint(0, 3)
        p.contract = flat_contract(
            salary, years, world.season_year - signed_offset,
            years_with_team=rng.randint(0, 4),
        )


def _free_agent_potential(rng: Rng, ovr: int, age: int) -> int:
    """Potential for the opening free-agent pool.

    The age-based curve in :func:`make_player` is right for rostered young players and draft
    prospects, but it has no place here: at a fresh start, undrafted blue-chips don't float in
    free agency — they're on a roster or still in the draft. Free agents are leftover talent, so
    upside is modest and stays clear of star territory. A good-but-aging veteran sitting at his
    ceiling (an 80/80 guy) is fine; what we never want is a 60-overall kid projected to 90+. The
    rare diamond-in-the-rough is the only exception, and even he tops out well short of stardom.
    """
    if age >= 25:
        return int(min(85, ovr + rng.randint(0, 1)))
    mu = max(0.0, (24 - age) * 1.1)
    upside = max(0.0, rng.gauss(mu, mu * 0.4 + 1.5))
    ceiling = 86 if rng.chance(0.03) else 79
    return int(max(ovr, min(round(ovr + upside), ceiling)))


def _build_free_agents(world: World, names: NameGenerator) -> None:
    for _ in range(_NUM_FREE_AGENTS):
        target = int(max(45, min(80, round(world.rng.gauss(62, 8)))))
        # Fewer young longshots than a roster carries — the opening pool skews toward aging vets.
        is_young = world.rng.chance(0.22)
        age = (world.rng.randint(*ROOKIE_AGE_RANGE) if is_young
               else int(min(38, max(23, round(world.rng.triangular(23, 38, 30))))))
        p = make_player(world.rng, world.new_pid(), names, target_overall=target, age=age)
        p.potential = _free_agent_potential(world.rng, p.overall, p.age)
        p.team_id = None
        world.add_player(p)
        world.free_agents.append(p.pid)


def build_world(seed: int = None, season_preset: str = DEFAULT_SEASON_PRESET,
                backstory: bool = True) -> World:
    """Generate a complete, ready-to-play league world (no user team selected yet)."""
    # Always pin a concrete seed so the world is reproducible and shareable, even when the
    # caller didn't pick one.
    if seed is None:
        seed = random.randrange(1 << 30)
    rng = Rng(seed)
    world = World(rng=rng)
    world.season_year = 2025
    world.season_games = SEASON_PRESETS.get(season_preset, SEASON_PRESETS[DEFAULT_SEASON_PRESET])
    world.phase = Phase.PRESEASON

    names = NameGenerator(rng)
    # Coaches draw from a *separate* rng so adding them never perturbs the roster/contract/draft
    # stream — every existing seed reproduces the exact same league, just with coaches layered on.
    coach_rng = Rng(None if seed is None else seed ^ 0xC0AC)
    coach_names = NameGenerator(coach_rng)
    for tid, rec in enumerate(_load_team_records()):
        team = Team(
            tid=tid,
            city=rec["city"],
            name=rec["name"],
            abbrev=rec["abbrev"],
            conference=rec["conference"],
            color=rec.get("color", "white"),
            market_size=rec.get("market_size", 3),
        )
        world.register_team(team)
        _build_roster(world, team, names)
        team.coach = assign_coach(coach_rng, coach_names.name()[1])
        apply_coach_tactics(team)

    _build_free_agents(world, names)

    from hoopsim.systems.draft_system import init_draft_picks
    init_draft_picks(world)

    # Layer synthetic history on top — fabricated career arcs for veterans plus a retired-legends
    # cohort — using a separate rng so the league above is byte-for-byte the same with or without it.
    if backstory:
        from hoopsim.gen.backstory import apply_backstory
        apply_backstory(world, seed)
    return world
