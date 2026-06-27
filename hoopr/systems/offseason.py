"""Offseason orchestration: archive the year, roll contracts, age/retire, reload next season.

Development, the draft, and free-agent bidding are wired in here as the systems land. The order
is: archive → expire contracts → age/retire → develop → draft → free agency → fill rosters →
start the next regular season.
"""
from __future__ import annotations

from typing import List

from hoopr.config import RETIREMENT_AGE, ROSTER_MAX, ROSTER_MIN, VETERAN_MINIMUM
from hoopr.models.contract import flat_contract
from hoopr.models.league import conference_standings
from hoopr.models.world import World
from hoopr.sim.season import start_season


def archive_season(world: World, champion_tid) -> None:
    from hoopr.systems import awards
    standings = {conf: [t.tid for t in conference_standings(world.team_list(), conf)]
                 for conf in ("East", "West")}
    # Awards must be computed before careers roll over (rookies still have empty career,
    # most-improved can still see last season's overall).
    world.history.append({
        "year": world.season_year,
        "champion": champion_tid,
        "champion_name": world.teams[champion_tid].full_name if champion_tid in world.teams else "",
        "standings": standings,
        "awards": awards.compute_awards(world),
    })
    for p in world.players.values():
        if p.season.gp > 0:
            team = world.teams.get(p.team_id)
            p.career.append({
                "year": world.season_year,
                "team": team.abbrev if team else "FA",
                "gp": p.season.gp, "ppg": round(p.season.ppg, 1),
                "rpg": round(p.season.rpg, 1), "apg": round(p.season.apg, 1),
                "ovr": p.overall,
            })


def expire_contracts(world: World) -> List[int]:
    """Advance every rostered contract a year; return pids that hit free agency."""
    new_fas: List[int] = []
    for team in world.team_list():
        for pid in list(team.roster):
            contract = world.players[pid].contract
            contract.advance_year()
            if contract.years_remaining == 0:
                new_fas.append(pid)
    for pid in new_fas:
        world.release_player(pid)
    return new_fas


def age_and_retire(world: World) -> List[int]:
    retired: List[int] = []
    for p in list(world.players.values()):
        p.age += 1
        force = p.age >= RETIREMENT_AGE
        decline = p.age >= 35 and p.overall < 68 and world.rng.chance(0.5)
        if force or decline:
            retired.append(p.pid)
    for pid in retired:
        p = world.players.pop(pid)
        if p.team_id in world.teams:
            world.teams[p.team_id].remove_player(pid)
        if pid in world.free_agents:
            world.free_agents.remove(pid)
    return retired


def enforce_roster_max(world: World) -> None:
    """Waive the lowest-rated players from any team that is over the roster maximum.

    Draft picks can push a team that didn't shed salary above the limit; waived players go to
    free agency where they can latch on elsewhere.
    """
    for team in world.team_list():
        while len(team.roster) > ROSTER_MAX:
            worst = min(team.roster, key=lambda pid: world.players[pid].overall)
            world.release_player(worst)


def fill_rosters(world: World) -> None:
    """Ensure every team meets the roster minimum by signing minimum-deal free agents."""
    for team in world.team_list():
        while len(team.roster) < ROSTER_MIN and world.free_agents:
            best = max(world.free_agents, key=lambda pid: world.players[pid].overall)
            contract = flat_contract(VETERAN_MINIMUM, 1, world.season_year + 1)
            world.sign_player(best, team.tid, contract)


def pre_draft(world: World, champion_tid) -> dict:
    """Archive the year, develop players, expire contracts, age and retire. (Pre-draft.)"""
    archive_season(world, champion_tid)
    for team in world.team_list():
        team.mle_used = False          # each team gets its one mid-level exception back
    from hoopr.systems import development
    development.develop_all(world)
    new_fas = expire_contracts(world)
    retired = age_and_retire(world)
    return {"new_fas": len(new_fas), "retired": len(retired)}


def cull_free_agents(world: World, keep: int = 80) -> int:
    """Keep the league population bounded: unsigned, lowest-rated free agents leave the league."""
    if len(world.free_agents) <= keep:
        return 0
    ranked = sorted(world.free_agents,
                    key=lambda pid: world.players[pid].overall, reverse=True)
    cut = ranked[keep:]
    for pid in cut:
        world.free_agents.remove(pid)
        world.players.pop(pid, None)
    return len(cut)


def post_offseason(world: World) -> None:
    """Fill rosters to the minimum, cull the free-agent pool, grow the cap, and start next year."""
    from hoopr.config import CAP_GROWTH_RATE
    from hoopr.systems import cap
    from hoopr.systems import draft_system
    fill_rosters(world)
    cull_free_agents(world)
    cap.grow_cap(world, CAP_GROWTH_RATE)
    world.season_year += 1
    draft_system.roll_draft_picks(world)
    world.draft_class = None        # retire this year's class so next offseason starts clean
    start_season(world)


def run_offseason(world: World, champion_tid) -> dict:
    """Headless: run the full offseason (AI for every team) and start the next season."""
    summary = pre_draft(world, champion_tid)

    from hoopr.systems import draft_system
    draft_summary = draft_system.run_offseason_draft(world)
    enforce_roster_max(world)

    from hoopr.systems import freeagency
    fa_summary = freeagency.run_free_agency(world)

    post_offseason(world)
    summary.update({"draft": draft_summary, "free_agency": fa_summary})
    return summary
