"""Draft class generation, lottery-weighted order, and selection logic."""
from __future__ import annotations

from typing import List

from hoopsim.config import FUTURE_PICK_YEARS, ROOKIE_CONTRACT_YEARS, ROOKIE_SCALE
from hoopsim.gen.namegen import NameGenerator
from hoopsim.gen.playergen import make_player
from hoopsim.models.contract import flat_contract
from hoopsim.models.draft import DraftClass, DraftPick
from hoopsim.models.league import Phase
from hoopsim.models.team import auto_set_lineup
from hoopsim.models.world import World

PROSPECTS = 70


# ---------------------------------------------------------------------------
# Generation & ordering
# ---------------------------------------------------------------------------
def generate_draft_class(world: World) -> List[int]:
    names = NameGenerator(world.rng)
    ids: List[int] = []
    for i in range(PROSPECTS):
        base = 75 - i * 0.34
        target = int(max(48, min(80, round(base + world.rng.gauss(0, 3.0)))))
        p = make_player(world.rng, world.new_pid(), names,
                        target_overall=target, is_prospect=True)
        p.team_id = None
        world.add_player(p)
        ids.append(p.pid)
    ids.sort(key=lambda pid: prospect_rank(world.players[pid]), reverse=True)
    return ids


def prospect_rank(player) -> float:
    return 0.45 * player.overall + 0.55 * player.scouted_potential()


# ---------------------------------------------------------------------------
# Tradeable future picks
# ---------------------------------------------------------------------------
def init_draft_picks(world: World) -> None:
    """Give every team its own first- and second-round picks for the next few drafts."""
    world.draft_picks = []
    for tid in world.teams:
        for year in range(world.season_year, world.season_year + FUTURE_PICK_YEARS):
            for rnd in (1, 2):
                world.draft_picks.append(DraftPick(year=year, round=rnd,
                                                   original_tid=tid, owner_tid=tid))


def roll_draft_picks(world: World) -> None:
    """After a draft year ends: drop spent picks and add a new far-future pick per team.

    Keeps a rolling ``FUTURE_PICK_YEARS`` window of tradeable picks. Traded picks already in
    the window are untouched; the brand-new far-out picks always start owned by their own team.
    """
    if not world.draft_picks:
        init_draft_picks(world)
        return
    world.draft_picks = [p for p in world.draft_picks if p.year >= world.season_year]
    far = world.season_year + FUTURE_PICK_YEARS - 1
    for tid in world.teams:
        for rnd in (1, 2):
            if world.find_pick(far, rnd, tid) is None:
                world.draft_picks.append(DraftPick(year=far, round=rnd,
                                                   original_tid=tid, owner_tid=tid))


def _weighted_lottery(world: World, teams_worst_first: list) -> list:
    pool = list(teams_worst_first)
    weights = {t.tid: (len(pool) - i) ** 1.3 for i, t in enumerate(pool)}
    result = []
    while pool:
        pick = world.rng.weighted_one(pool, [weights[t.tid] for t in pool])
        result.append(pick)
        pool.remove(pick)
    return result


def compute_draft_order(world: World) -> List[int]:
    """The original-team slot order (worst-first, lottery for round 1), ignoring ownership."""
    seeds = world.bracket.get("seeds", {}) if world.bracket else {}
    playoff_tids = {int(k) for k in seeds.keys()}
    worst_first = sorted(world.team_list(), key=lambda t: t.win_pct)
    non_playoff = [t for t in worst_first if t.tid not in playoff_tids]
    playoff_worst_first = [t for t in worst_first if t.tid in playoff_tids]
    lottery = _weighted_lottery(world, non_playoff)
    round1 = [t.tid for t in lottery] + [t.tid for t in playoff_worst_first]
    round2 = [t.tid for t in worst_first]
    return round1 + round2


def _pick_owner(world: World, year: int, rnd: int, original_tid: int) -> int:
    """Who actually selects in this slot — the current owner of the pick, else the original team."""
    pick = world.find_pick(year, rnd, original_tid)
    return pick.owner_tid if pick is not None else original_tid


def setup_draft(world: World) -> DraftClass:
    prospects = generate_draft_class(world)
    origins = compute_draft_order(world)
    n_teams = len(world.teams)
    # First n_teams slots are round 1, the rest round 2 (compute_draft_order builds R1 then R2).
    order = [_pick_owner(world, world.season_year, 1 if i < n_teams else 2, orig)
             for i, orig in enumerate(origins)]
    dc = DraftClass(year=world.season_year, prospect_ids=prospects,
                    order=order, origins=origins, current_pick=1)
    world.draft_class = dc
    world.phase = Phase.DRAFT
    return dc


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------
def rookie_salary(pick_no: int) -> int:
    points = sorted(ROOKIE_SCALE.keys())
    if pick_no <= points[0]:
        return ROOKIE_SCALE[points[0]]
    if pick_no >= points[-1]:
        return ROOKIE_SCALE[points[-1]]
    lo = max(p for p in points if p <= pick_no)
    hi = min(p for p in points if p >= pick_no)
    if lo == hi:
        return ROOKIE_SCALE[lo]
    frac = (pick_no - lo) / (hi - lo)
    value = ROOKIE_SCALE[lo] + frac * (ROOKIE_SCALE[hi] - ROOKIE_SCALE[lo])
    return int(round(value / 100_000) * 100_000)


def make_pick(world: World, pid: int) -> None:
    dc = world.draft_class
    pick_no = dc.current_pick
    tid = dc.team_on_clock()
    salary = rookie_salary(pick_no)
    contract = flat_contract(salary, ROOKIE_CONTRACT_YEARS, world.season_year, rookie_scale=True)
    world.sign_player(pid, tid, contract)
    dc.record_pick(pid)


def best_available(world: World) -> int:
    dc = world.draft_class
    remaining = dc.remaining_prospects()
    return max(remaining, key=lambda pid: prospect_rank(world.players[pid]))


def ai_pick(world: World) -> int:
    pid = best_available(world)
    make_pick(world, pid)
    return pid


def auto_complete_draft(world: World) -> None:
    dc = world.draft_class
    while not dc.complete:
        ai_pick(world)


def undrafted_to_free_agents(world: World) -> None:
    dc = world.draft_class
    for pid in dc.remaining_prospects():
        if pid not in world.free_agents:
            world.free_agents.append(pid)
    for team in world.team_list():
        auto_set_lineup(team, world.players)


def run_offseason_draft(world: World) -> dict:
    """Headless: build the class, auto-run all picks, send undrafted to free agency."""
    setup_draft(world)
    total = world.draft_class.total_picks
    auto_complete_draft(world)
    undrafted_to_free_agents(world)
    return {"picks": total}
