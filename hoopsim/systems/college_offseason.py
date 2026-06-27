"""College offseason: development, eligibility (declare/graduate/return), the NBA draft
pipeline, recruiting, and rolling into the next college season.

This is where the *college → NBA pipeline* pays off: underclassmen with NBA stock and graduating
seniors declare for the draft, and the background NBA teams select them.
"""
from __future__ import annotations

from typing import List, Tuple

from hoopsim.config import RETIREMENT_AGE, ROSTER_MAX, ROOKIE_CONTRACT_YEARS
from hoopsim.gen.collegegen import generate_recruit_class
from hoopsim.models.contract import flat_contract
from hoopsim.models.player import Player
from hoopsim.models.team import auto_set_lineup
from hoopsim.models.world import World
from hoopsim.sim.season import start_season
from hoopsim.systems import collegefin, development, recruiting
from hoopsim.systems.draft_system import prospect_rank, rookie_salary


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------
def declare_decision(world: World, p: Player) -> str:
    """Return 'declare' (enter NBA draft), 'return' (another college year), or 'graduate'."""
    stock = 0.5 * p.overall + 0.5 * p.scouted_potential()
    if p.class_year >= 4:
        return "declare" if stock >= 66 else "graduate"
    threshold = {1: 84, 2: 80, 3: 76}.get(p.class_year, 78)
    if stock >= threshold and world.rng.chance(0.5 + (stock - threshold) * 0.05):
        return "declare"
    return "return"


def run_eligibility(world: World) -> Tuple[List[int], int, int]:
    """Resolve every college player's status. Returns (declared_pids, returning, graduated)."""
    declared: List[int] = []
    returning = graduated = 0
    for team in world.team_list():
        for pid in list(team.roster):
            p = world.players[pid]
            decision = declare_decision(world, p)
            if decision == "declare":
                team.remove_player(pid)
                p.team_id = None
                p.class_year = 0
                declared.append(pid)
            elif decision == "graduate":
                team.remove_player(pid)
                world.players.pop(pid, None)
                graduated += 1
            else:  # return
                p.class_year += 1
                p.age += 1
                returning += 1
    return declared, returning, graduated


# ---------------------------------------------------------------------------
# NBA draft pipeline
# ---------------------------------------------------------------------------
def _background_nba_rollover(world: World) -> None:
    for team in world.other_team_list():
        for pid in list(team.roster):
            p = world.players[pid]
            p.age += 1
            if p.age >= RETIREMENT_AGE:
                team.remove_player(pid)
                world.players.pop(pid, None)
        development_pids = [world.players[pid] for pid in team.roster]
        for p in development_pids:
            development.develop_player(p, world.rng)


def _trim_background_rosters(world: World) -> None:
    for team in world.other_team_list():
        while len(team.roster) > ROSTER_MAX:
            worst = min(team.roster, key=lambda pid: world.players[pid].overall)
            team.remove_player(worst)
            world.players.pop(worst, None)
        auto_set_lineup(team, world.players)


def run_nba_draft_pipeline(world: World, declared: List[int]) -> dict:
    """Background NBA teams draft the declared players. Returns a pipeline summary for the UI."""
    _background_nba_rollover(world)
    order = world.other_team_list()
    world.rng.shuffle(order)
    order = order + order            # two rounds
    pool = sorted(declared, key=lambda pid: prospect_rank(world.players[pid]), reverse=True)

    results = []
    for pick_no, team in enumerate(order, start=1):
        if not pool:
            break
        pid = pool.pop(0)
        p = world.players[pid]
        salary = rookie_salary(pick_no)
        p.contract = flat_contract(salary, ROOKIE_CONTRACT_YEARS, world.season_year,
                                   rookie_scale=True)
        p.team_id = team.tid
        p.experience = 0
        team.add_player(pid)
        results.append({"pick": pick_no, "tid": team.tid, "pid": pid,
                        "name": p.name, "college": p.college})

    drafted = {r["pid"] for r in results}
    # undrafted declarers don't make the NBA — they leave the player pool
    for pid in declared:
        if pid not in drafted:
            world.players.pop(pid, None)

    _trim_background_rosters(world)
    world.pipeline = {"year": world.season_year, "results": results}
    return {"drafted": len(results), "declared": len(declared)}


# ---------------------------------------------------------------------------
# Offseason orchestration (UI-driven in pieces; run_* is headless)
# ---------------------------------------------------------------------------
def pre_recruiting(world: World, champion_tid) -> dict:
    """Archive, develop, run eligibility + the NBA draft pipeline, and open recruiting."""
    if champion_tid is not None and champion_tid in world.teams:
        world.history.append({"year": world.season_year, "champion": champion_tid,
                              "champion_name": world.teams[champion_tid].full_name})
    development.develop_all(world)          # develops college players toward potential
    collegefin.grow_brand_values(world)
    declared, returning, graduated = run_eligibility(world)
    pipeline = run_nba_draft_pipeline(world, declared)
    generate_recruit_class(world)
    return {"declared": len(declared), "returning": returning, "graduated": graduated,
            "drafted": pipeline["drafted"]}


def post_recruiting(world: World) -> None:
    recruiting.fill_college_rosters(world)
    world.season_year += 1
    start_season(world)


def run_college_offseason(world: World, champion_tid) -> dict:
    """Headless college offseason (AI recruiting only)."""
    summary = pre_recruiting(world, champion_tid)
    recruit_summary = recruiting.resolve_recruiting(world, {})
    post_recruiting(world)
    summary["recruited"] = recruit_summary["total"]
    return summary
