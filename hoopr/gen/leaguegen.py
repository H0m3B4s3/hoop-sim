"""World generation — build a full league of teams, rosters, contracts, and free agents."""
from __future__ import annotations

import json
import os
from typing import List

from hoopr.config import (DEFAULT_SEASON_PRESET, ROOKIE_AGE_RANGE, SALARY_CAP, SEASON_PRESETS,
                          VETERAN_MINIMUM)
from hoopr.gen.namegen import NameGenerator
from hoopr.gen.playergen import make_player
from hoopr.models.contract import flat_contract
from hoopr.models.league import Phase
from hoopr.models.player import Player
from hoopr.models.team import Team, auto_set_lineup
from hoopr.models.world import World
from hoopr.rng import Rng

_TEAMS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "teams.json")

# Talent curve: target overall per roster slot (best -> worst) for a 14-man roster.
_ROSTER_CURVE = [86, 81, 78, 75, 73, 71, 69, 67, 65, 63, 61, 60, 58, 57]
_NUM_FREE_AGENTS = 70


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

    for slot, base in enumerate(_ROSTER_CURVE):
        noise = rng.gauss(0.0, 2.5)
        star_bonus = rng.uniform(-2.0, 6.0) if slot == 0 else 0.0
        target = int(max(50, min(95, round(base + team_strength + noise + star_bonus))))
        p = make_player(world.rng, world.new_pid(), names, target_overall=target)
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


def _build_free_agents(world: World, names: NameGenerator) -> None:
    for _ in range(_NUM_FREE_AGENTS):
        target = int(max(45, min(80, round(world.rng.gauss(62, 8)))))
        is_young = world.rng.chance(0.35)
        age = (world.rng.randint(*ROOKIE_AGE_RANGE) if is_young
               else int(min(38, max(23, round(world.rng.triangular(23, 38, 30))))))
        p = make_player(world.rng, world.new_pid(), names, target_overall=target, age=age)
        p.team_id = None
        world.add_player(p)
        world.free_agents.append(p.pid)


def build_world(seed: int = None, season_preset: str = DEFAULT_SEASON_PRESET) -> World:
    """Generate a complete, ready-to-play league world (no user team selected yet)."""
    rng = Rng(seed)
    world = World(rng=rng)
    world.season_year = 2025
    world.season_games = SEASON_PRESETS.get(season_preset, SEASON_PRESETS[DEFAULT_SEASON_PRESET])
    world.phase = Phase.PRESEASON

    names = NameGenerator(rng)
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

    _build_free_agents(world, names)
    return world
