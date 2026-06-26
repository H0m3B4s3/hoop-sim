"""College-mode world generation.

Builds a college-primary world: college programs with class-year rosters (the user's league),
a pool of high-school recruits, and a background NBA (stored in ``world.other_teams``) that
exists to draft players coming through the pipeline. College players are amateurs — lower current
overall but high upside, with marketability that matters in NIL mode.
"""
from __future__ import annotations

import json
import os
from typing import List

from hoopr.config import DEFAULT_COLLEGE_ECONOMY
from hoopr.gen.leaguegen import _build_roster as build_nba_roster
from hoopr.gen.leaguegen import _load_team_records
from hoopr.gen.namegen import NameGenerator
from hoopr.gen.playergen import make_player
from hoopr.models.league import Phase
from hoopr.models.player import Player
from hoopr.models.team import Team, auto_set_lineup
from hoopr.models.world import World
from hoopr.rng import Rng

_NAMES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "college_names.json")

COLLEGE_SEASON_GAMES = 28
NBA_TID_OFFSET = 200               # keep background-NBA ids clear of college ids
_RECRUITS = 90
TEAMS_PER_CONFERENCE = 8

# 8 conferences across three tiers: power (blue bloods), mid-major, low-major.
COLLEGE_CONFERENCES = [
    ("Atlantic", "power"), ("Continental", "power"),
    ("Heartland", "mid"), ("Pacific", "mid"), ("Summit", "mid"),
    ("Frontier", "low"), ("Coastal", "low"), ("Highland", "low"),
]
_TIER_PRESTIGE = {"power": (3, 5), "mid": (2, 4), "low": (1, 2)}

# 13-man roster class distribution (Fr, So, Jr, Sr) and a descending talent curve.
_CLASS_PLAN = [1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 4, 4, 4]
_ROSTER_CURVE = [74, 71, 69, 67, 65, 63, 61, 60, 58, 57, 55, 54, 52]


def _load_name_pools() -> dict:
    with open(_NAMES_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _make_abbrev(place: str, mascot: str, used: set) -> str:
    letters = [c for c in place.upper() if c.isalpha()]
    base = "".join(letters[:3]) if len(letters) >= 3 else (place.upper() + mascot.upper())[:3]
    abbr = base
    i = 0
    while abbr in used:
        i += 1
        abbr = (base[:2] + mascot.upper()[i % len(mascot)]).upper()
    used.add(abbr)
    return abbr


def _generate_college_records(rng: Rng) -> List[dict]:
    pools = _load_name_pools()
    places = list(pools["places"])
    mascots = list(pools["mascots"])
    colors = list(pools["colors"])
    rng.shuffle(places)
    rng.shuffle(mascots)
    records: List[dict] = []
    used_abbr: set = set()
    pi = mi = 0
    for conf, tier in COLLEGE_CONFERENCES:
        lo, hi = _TIER_PRESTIGE[tier]
        for slot in range(TEAMS_PER_CONFERENCE):
            place = places[pi % len(places)]; pi += 1
            mascot = mascots[mi % len(mascots)]; mi += 1
            prestige = 5 if (tier == "power" and slot == 0) else rng.randint(lo, hi)
            records.append({
                "city": place, "name": mascot,
                "abbrev": _make_abbrev(place, mascot, used_abbr),
                "conference": conf, "color": rng.choice(colors), "prestige": prestige,
            })
    return records


def class_label(class_year: int) -> str:
    return {1: "Fr", 2: "So", 3: "Jr", 4: "Sr"}.get(class_year, "--")


def star_rating(player: Player) -> int:
    """A 1-5 recruiting/upside star rating derived from scouted potential."""
    pot = player.scouted_potential()
    if pot >= 88:
        return 5
    if pot >= 82:
        return 4
    if pot >= 75:
        return 3
    if pot >= 68:
        return 2
    return 1


def make_college_player(world: World, names: NameGenerator, team: Team,
                        class_year: int, target_overall: int) -> Player:
    age = 17 + class_year                       # Fr 18 .. Sr 21
    p = make_player(world.rng, world.new_pid(), names,
                    target_overall=target_overall, age=age, is_prospect=True)
    p.class_year = class_year
    p.college = team.full_name
    p.team_id = team.tid
    p.brand_value = p.ratings["marketability"] * world.rng.randint(300, 1500)
    return p


def _build_college_roster(world: World, team: Team, names: NameGenerator) -> None:
    prestige_bonus = (team.prestige - 3) * 2.0
    classes = list(_CLASS_PLAN)
    world.rng.shuffle(classes)
    for base, class_year in zip(_ROSTER_CURVE, classes):
        target = int(max(46, min(86, round(base + prestige_bonus + world.rng.gauss(0, 2.5)))))
        p = make_college_player(world, names, team, class_year, target)
        world.add_player(p)
        team.add_player(p.pid)
    auto_set_lineup(team, world.players)
    team.nil_budget = int(team.prestige * world.rng.uniform(0.8, 1.4) * 1_000_000)


def _build_recruits(world: World, names: NameGenerator) -> None:
    for _ in range(_RECRUITS):
        target = int(max(44, min(70, round(world.rng.gauss(56, 6)))))
        p = make_player(world.rng, world.new_pid(), names, target_overall=target, age=18,
                        is_prospect=True)
        p.class_year = 0                        # uncommitted high-schooler
        p.team_id = None
        p.college = ""
        p.brand_value = p.ratings["marketability"] * world.rng.randint(200, 900)
        world.add_player(p)
        world.recruits.append(p.pid)


def generate_recruit_class(world: World) -> None:
    """Generate a fresh high-school recruit pool for the upcoming cycle."""
    _build_recruits(world, NameGenerator(world.rng))


def _build_background_nba(world: World, names: NameGenerator) -> None:
    for i, rec in enumerate(_load_team_records()):
        team = Team(
            tid=NBA_TID_OFFSET + i,
            city=rec["city"], name=rec["name"], abbrev=rec["abbrev"],
            conference=rec["conference"], color=rec.get("color", "white"),
            market_size=rec.get("market_size", 3), league="nba",
        )
        world.register_other_team(team)
        build_nba_roster(world, team, names)


def build_college_world(seed: int = None, economy: str = DEFAULT_COLLEGE_ECONOMY) -> World:
    """Generate a complete college-primary world (no user team selected yet)."""
    rng = Rng(seed)
    world = World(rng=rng)
    world.mode = "college"
    world.college_economy = economy if economy in ("scholarship", "nil") else DEFAULT_COLLEGE_ECONOMY
    world.season_year = 2025
    world.season_games = COLLEGE_SEASON_GAMES
    world.phase = Phase.PRESEASON

    names = NameGenerator(rng)
    for tid, rec in enumerate(_generate_college_records(rng)):
        team = Team(
            tid=tid, city=rec["city"], name=rec["name"], abbrev=rec["abbrev"],
            conference=rec["conference"], color=rec.get("color", "white"),
            prestige=rec.get("prestige", 3), league="college",
        )
        world.register_team(team)
        _build_college_roster(world, team, names)

    _build_recruits(world, names)
    _build_background_nba(world, names)
    return world
