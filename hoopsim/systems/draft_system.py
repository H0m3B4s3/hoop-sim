"""Draft class generation, lottery-weighted order, and selection logic."""
from __future__ import annotations

from typing import List

from hoopsim.config import (FUTURE_PICK_YEARS, ROOKIE_AGE_RANGE, ROOKIE_CONTRACT_YEARS,
                            ROOKIE_SCALE)
from hoopsim.gen.namegen import NameGenerator
from hoopsim.gen.playergen import make_player
from hoopsim.models.contract import flat_contract
from hoopsim.models.draft import DraftClass, DraftPick
from hoopsim.models.league import Phase
from hoopsim.models.team import auto_set_lineup
from hoopsim.models.world import World

PROSPECTS = 70

# --- Draft-class talent shape --------------------------------------------------
# Each class gets its own ceiling and depth so seasons feel different: most years carry one or
# two genuine blue-chippers atop a steep cliff, the occasional loaded class runs deep, and a
# down year produces a #1 who is merely solid. POT for the prospect ranked ``i`` (0-based) is
#     top - depth * (CLIFF*(1 - e**(-i/CLIFF_TAU)) + TAIL*i) + noise
# i.e. a sharp early drop that saturates, plus a gentle linear tail for the back of the board.
_POT_CLIFF = 11.0       # magnitude of the early talent cliff (top picks → mid-70s ceilings)
_POT_CLIFF_TAU = 2.0    # how quickly the cliff bites (smaller = steeper)
_POT_TAIL = 0.13        # slow linear decay across the rest of the board


def _class_profile(rng) -> tuple:
    """Roll this draft's ceiling and depth.

    ``top`` is the #1 prospect's potential; its Gaussian tails are what make a class loaded or
    weak. ``depth`` scales the whole decay curve: < 1 stretches talent deep into the board,
    > 1 collapses it onto the very top picks.
    """
    top = max(77.0, min(90.0, rng.gauss(84.0, 3.2)))
    depth = max(0.82, min(1.4, rng.gauss(1.0, 0.22)))
    return top, depth


def _prospect_potential(rng, top: float, depth: float, rank: int) -> int:
    import math
    cliff = _POT_CLIFF * (1.0 - math.exp(-rank / _POT_CLIFF_TAU))
    drop = depth * (cliff + _POT_TAIL * rank)
    return int(round(max(55.0, min(95.0, top - drop + rng.gauss(0, 1.7)))))


# ---------------------------------------------------------------------------
# Generation & ordering
# ---------------------------------------------------------------------------
def generate_draft_class(world: World) -> List[int]:
    names = NameGenerator(world.rng)
    rng = world.rng
    top, depth = _class_profile(rng)
    ids: List[int] = []
    for i in range(PROSPECTS):
        pot = _prospect_potential(rng, top, depth, i)
        age = rng.randint(*ROOKIE_AGE_RANGE)
        # Current ability trails potential by a youth gap — younger prospects are rawer, so the
        # gap is bigger; the floor keeps a few polished, NBA-ready picks each year.
        gap = max(2.0, min(22.0, rng.gauss(13.0 - (age - 19) * 2.0, 3.0)))
        target = int(max(48, min(86, round(pot - gap))))
        p = make_player(rng, world.new_pid(), names, age=age,
                        target_overall=target, is_prospect=True)
        p.team_id = None
        p.potential = max(p.overall, pot)
        p.pre_draft = _pre_draft_stats(rng, p)
        world.add_player(p)
        ids.append(p.pid)
    # Board order follows scouted talent, which only loosely tracks true potential (fog of war):
    # a polished prospect can out-rank a rawer one with a higher ceiling.
    ids.sort(key=lambda pid: prospect_rank(world.players[pid]), reverse=True)
    return ids


def prospect_rank(player) -> float:
    return 0.45 * player.overall + 0.55 * player.scouted_potential()


# Where a prospect played before the draft — pure flavor, weighted toward big programs.
_PRE_DRAFT_LEVELS = [
    ("NCAA — Power Conf", 0.52), ("NCAA — Mid-Major", 0.22),
    ("International", 0.18), ("G League Ignite", 0.08),
]


def _pre_draft_stats(rng, p) -> dict:
    """A plausible per-game college/international line inferred from a prospect's ratings.

    Not used by the engine — it gives the user a scouting profile to read alongside the
    archetype, and (like real pre-draft stats) it's only a loose proxy for pro potential.
    """
    r = p.ratings
    big = p.position in ("PF", "C")
    guard = p.position in ("PG", "SG")
    scoring = 0.45 * r["finishing"] + 0.30 * r["three_point"] + 0.25 * r["mid_range"]
    usage = 0.6 * r["ball_handle"] + 0.4 * r["off_iq"]
    ppg = 9.0 + (scoring - 60) * 0.55 + (usage - 60) * 0.06 + rng.gauss(0, 1.8)
    fc = 1.25 if big else (1.0 if p.position == "SF" else 0.78)
    rpg = 2.0 + r["rebounding"] * fc * 0.072 + rng.gauss(0, 0.7)
    gf = 1.2 if guard else (0.85 if p.position == "SF" else 0.55)
    apg = 0.8 + (r["passing"] * 0.05 + r["ball_handle"] * 0.025) * gf + rng.gauss(0, 0.5)
    spg = 0.3 + r["steal"] * 0.018 + rng.gauss(0, 0.2)
    bpg = 0.2 + r["block"] * (0.03 if big else 0.01) + rng.gauss(0, 0.2)
    fg = 0.40 + (r["finishing"] - 60) * 0.0026 + (0.03 if big else 0.0)
    tp = 0.27 + (r["three_point"] - 55) * 0.0028
    games = rng.randint(24, 35)
    level = rng.weighted_one([lv for lv, _ in _PRE_DRAFT_LEVELS],
                             [w for _, w in _PRE_DRAFT_LEVELS])
    return {
        "level": level,
        "gp": games,
        "ppg": round(max(2.0, ppg), 1),
        "rpg": round(max(1.0, rpg), 1),
        "apg": round(max(0.3, apg), 1),
        "spg": round(max(0.1, spg), 1),
        "bpg": round(max(0.0, bpg), 1),
        "fg_pct": round(min(0.68, max(0.34, fg)), 3),
        "tp_pct": round(min(0.50, max(0.18, tp)), 3),
    }


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
    # Record draft provenance (bio flavor): round and overall pick from the slot.
    n_teams = len(world.teams)
    team = world.teams.get(tid)
    world.players[pid].draft = {
        "year": dc.year,
        "round": 1 if pick_no <= n_teams else 2,
        "pick": pick_no,
        "team": team.abbrev if team else "",
    }
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
