"""Offseason orchestration: archive the year, roll contracts, age/retire, reload next season.

Development, the draft, and free-agent bidding are wired in here as the systems land. The order
is: archive → expire contracts → age/retire → develop → draft → free agency → fill rosters →
start the next regular season.
"""
from __future__ import annotations

from typing import List

from hoopsim.config import RETIREMENT_AGE, ROSTER_MAX, ROSTER_MIN, VETERAN_MINIMUM
from hoopsim.models import advanced
from hoopsim.models.contract import flat_contract
from hoopsim.models.league import conference_standings
from hoopsim.models.world import World
from hoopsim.sim.season import start_season


def archive_season(world: World, champion_tid) -> List[dict]:
    """Record the season into history, roll careers, accrue accolades. Returns milestone events."""
    from hoopsim.systems import awards, legacy, news
    standings = {conf: [t.tid for t in conference_standings(world.team_list(), conf)]
                 for conf in ("East", "West")}
    # Awards must be computed before careers roll over (rookies still have empty career,
    # most-improved can still see last season's overall).
    season_awards = awards.compute_awards(world)
    world.history.append({
        "year": world.season_year,
        "champion": champion_tid,
        "champion_name": world.teams[champion_tid].full_name if champion_tid in world.teams else "",
        "standings": standings,
        "awards": season_awards,
    })
    # Tally each winner's personal accolades so career résumés stay self-contained for the HoF.
    legacy.record_accolades(world, season_awards, champion_tid)
    # Emit awards to the news wire
    award_labels = {
        "mvp": "MVP",
        "roy": "Rookie of the Year",
        "dpoy": "Defensive Player of the Year",
        "mip": "Most Improved Player",
        "smoy": "Sixth Man of the Year",
    }
    for key, label in award_labels.items():
        if key in season_awards:
            news.award(world, label, season_awards[key])
    # Emit champion to the news wire
    champion_team = world.teams.get(champion_tid)
    if champion_team:
        news.champion(world, champion_team)
    milestones: List[dict] = []
    for p in world.players.values():
        if p.season.gp > 0:
            team = world.teams.get(p.team_id)
            before = legacy.career_totals(p.career)
            p.career.append({
                "year": world.season_year,
                "team": team.abbrev if team else "FA",
                "gp": p.season.gp, "ppg": round(p.season.ppg, 1),
                "rpg": round(p.season.rpg, 1), "apg": round(p.season.apg, 1),
                "spg": round(p.season.per_game("stl"), 1),
                "bpg": round(p.season.per_game("blk"), 1),
                "topg": round(p.season.per_game("tov"), 1),
                "fg_pct": round(p.season.fg_pct, 3), "tp_pct": round(p.season.tp_pct, 3),
                "ft_pct": round(p.season.ft_pct, 3), "ts_pct": round(p.season.ts_pct, 3),
                "usg_pct": round(advanced.usage_pct(p.season, team.season_stats), 1) if team else 0.0,
                "ortg": round(advanced.player_ortg_proxy(
                    p.season, team.season_stats, team.opp_season_stats), 1) if team else 0.0,
                "drtg": round(advanced.player_drtg_proxy(
                    p.season, team.season_stats, team.opp_season_stats), 1) if team else 0.0,
                "ovr": p.overall,
            })
            # A completed pro season; experience drives salary tiers (cap.max_salary) and how
            # much scouting fog clears (systems.scouting). Without this it stayed frozen forever.
            p.experience += 1
            for ms in legacy.crossed_milestones(before, legacy.career_totals(p.career)):
                milestones.append({**ms, "pid": p.pid, "name": p.name})
    return milestones


def expire_contracts(world: World) -> List[int]:
    """Advance every rostered contract a year; return pids that hit free agency."""
    new_fas: List[int] = []
    for team in world.team_list():
        if team.dead_money:
            team.dead_money.pop(0)                  # this season's dead money comes off the books
        for pid in list(team.roster):
            contract = world.players[pid].contract
            contract.advance_year()
            if contract.years_remaining == 0:
                new_fas.append(pid)
    for pid in new_fas:
        world.release_player(pid)
    return new_fas


def age_and_retire(world: World) -> dict:
    """Age everyone a year, retire the old/declined, and freeze each retiree's legacy résumé.

    Returns ``{"retired": [pids], "inducted": [résumé snapshots]}``. Retirees are no longer simply
    dropped — :func:`legacy.retire` snapshots them into ``world.retired`` (and the Hall of Fame if
    they clear the bar) so their careers survive being removed from the active player pool.
    """
    from hoopsim.systems import legacy, news as news_module
    retiring: List[int] = []
    for p in list(world.players.values()):
        p.age += 1
        force = p.age >= RETIREMENT_AGE
        decline = p.age >= 35 and p.overall < 68 and world.rng.chance(0.5)
        if force or decline:
            retiring.append(p.pid)
    inducted: List[dict] = []
    for pid in retiring:
        p = world.players[pid]
        # Emit retirement before removing from world.players
        news_module.retirement(world, p)
        snap = legacy.retire(world, p)               # snapshot + (maybe) Hall of Fame induction
        if snap["hof"]:
            inducted.append(snap)
            # Emit Hall of Fame induction
            news_module.hall_of_fame(world, snap)
        world.players.pop(pid)
        if p.team_id in world.teams:
            world.teams[p.team_id].remove_player(pid)
        if pid in world.free_agents:
            world.free_agents.remove(pid)
    return {"retired": retiring, "inducted": inducted}


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
    from hoopsim.systems import owner
    # The owner judges the season on the roster and bracket as they finished, before anything moves.
    review = owner.review_season(world)
    milestones = archive_season(world, champion_tid)
    # Emit milestones to the news wire
    from hoopsim.systems import news as news_module
    for ms in milestones:
        news_module.milestone(world, ms)
    for team in world.team_list():
        team.mle_used = False          # each team gets its one mid-level exception back
    from hoopsim.systems import carousel, development, freeagency
    # The coaching carousel resolves first, on the record the season just produced, and before
    # development runs — so a team that hired a development coach gets him for this offseason's
    # growth rather than having to wait a full year for the hire to mean anything.
    carousel.record_coach_season(world)
    # A GM the owner just fired no longer runs the team: the AI handles its bench and its expiring
    # contracts this offseason, exactly as it would for any other club. The user picks a new job
    # (owner.take_job) before the draft.
    fired_from = world.user_team_id if review and review["fired"] else None
    if fired_from is not None:
        world.user_team_id = None
    try:
        coaching = carousel.run_carousel(world)
        development.develop_all(world)
        resigned = freeagency.run_retention(world)["resigned"]   # AI keeps its own before FA opens
    finally:
        if fired_from is not None:
            world.user_team_id = fired_from
    new_fas = expire_contracts(world)
    ar = age_and_retire(world)
    return {"new_fas": len(new_fas), "retired": len(ar["retired"]), "resigned": resigned,
            "inducted": ar["inducted"], "milestones": milestones,
            "coaching": coaching, "owner_review": review}


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
    from hoopsim.config import CAP_GROWTH_RATE
    from hoopsim.systems import cap
    from hoopsim.systems import draft_system, freeagency
    freeagency.end_fa_market(world)     # close any open wave before minimum-deal roster fill
    fill_rosters(world)
    cull_free_agents(world)
    cap.grow_cap(world, CAP_GROWTH_RATE)
    world.season_year += 1
    draft_system.roll_draft_picks(world)
    world.draft_class = None        # retire this year's class so next offseason starts clean
    from hoopsim.systems.momentum import offseason_reset
    offseason_reset(world)          # rust chemistry, drift morale toward baseline for the new year
    start_season(world)
    from hoopsim.systems import owner
    owner.begin_season(world)       # the owner sets this season's goal from the new roster


def run_offseason(world: World, champion_tid) -> dict:
    """Headless: run the full offseason (AI for every team) and start the next season."""
    summary = pre_draft(world, champion_tid)

    from hoopsim.systems import draft_system
    draft_summary = draft_system.run_offseason_draft(world)
    enforce_roster_max(world)

    from hoopsim.systems import freeagency
    fa_summary = freeagency.run_free_agency(world)

    post_offseason(world)
    summary.update({"draft": draft_summary, "free_agency": fa_summary})
    return summary
