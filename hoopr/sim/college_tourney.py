"""College postseason: single-elimination conference tournaments then a national tournament.

Bracket state lives on ``world.bracket`` as a JSON-native dict (``type == 'college'``) so it
serializes with the save. Games advance one slate (one game per live matchup) at a time so the
user can watch their own.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from hoopr.models.league import Game, Phase
from hoopr.models.world import World
from hoopr.sim.boxscore import GameResult
from hoopr.sim.season import sim_one

NATIONAL_FIELD = 16


# ---------------------------------------------------------------------------
# Bracket construction
# ---------------------------------------------------------------------------
def _seed_order(n: int) -> List[int]:
    """Standard single-elimination seed positions for a field of size n (power of two)."""
    order = [1, 2]
    while len(order) < n:
        m = len(order) * 2 + 1
        nxt: List[int] = []
        for x in order:
            nxt.extend([x, m - x])
        order = nxt
    return order


def _matchup(a: int, b: int) -> dict:
    return {"a": a, "b": b, "winner": None, "gid": None, "a_score": 0, "b_score": 0}


def build_single_elim(seeded_tids: List[int]) -> dict:
    """Build a single-elim bracket from teams already ordered best→worst seed."""
    n = len(seeded_tids)
    order = _seed_order(n)
    round1 = [_matchup(seeded_tids[order[i] - 1], seeded_tids[order[i + 1] - 1])
              for i in range(0, n, 2)]
    return {"rounds": [round1], "champion": None}


def _active_round(bracket: dict) -> Optional[List[dict]]:
    last = bracket["rounds"][-1]
    if any(m["winner"] is None for m in last):
        return last
    return None


def _advance_bracket(bracket: dict) -> None:
    last = bracket["rounds"][-1]
    if any(m["winner"] is None for m in last):
        return
    if len(last) == 1:
        bracket["champion"] = last[0]["winner"]
        return
    winners = [m["winner"] for m in last]
    bracket["rounds"].append([_matchup(winners[i], winners[i + 1])
                              for i in range(0, len(winners), 2)])


# ---------------------------------------------------------------------------
# Start postseason
# ---------------------------------------------------------------------------
def _conferences(world: World) -> List[str]:
    seen: List[str] = []
    for t in world.team_list():
        if t.conference not in seen:
            seen.append(t.conference)
    return seen


def _seeded_by_record(teams) -> List[int]:
    ordered = sorted(teams, key=lambda t: (-t.win_pct, -t.point_diff, t.tid))
    return [t.tid for t in ordered]


def start_college_postseason(world: World) -> List[str]:
    conf_brackets = {}
    log: List[str] = []
    for conf in _conferences(world):
        teams = [t for t in world.team_list() if t.conference == conf]
        seeds = _seeded_by_record(teams)[:8]
        conf_brackets[conf] = build_single_elim(seeds)
        log.append(f"{conf}: {len(seeds)}-team tournament")
    world.bracket = {"type": "college", "stage": "conf", "conf": conf_brackets,
                     "national": None, "champion": None}
    world.phase = Phase.PLAYOFFS
    return log


def _build_national_field(world: World) -> None:
    b = world.bracket
    champ_tids = [cb["champion"] for cb in b["conf"].values()]
    champs = set(champ_tids)
    at_large = [t for t in world.team_list() if t.tid not in champs]
    at_large_sorted = sorted(at_large, key=lambda t: (-t.win_pct, -t.point_diff, t.tid))
    field_tids = list(champ_tids) + [t.tid for t in at_large_sorted]
    field = field_tids[:NATIONAL_FIELD]
    # seed the whole field by record
    field_teams = [world.teams[tid] for tid in field]
    seeds = _seeded_by_record(field_teams)
    b["national"] = build_single_elim(seeds)
    b["national_field"] = seeds


# ---------------------------------------------------------------------------
# Advancement
# ---------------------------------------------------------------------------
def _play_round_slate(world: World, bracket: dict, watch_user: bool
                      ) -> Tuple[List[Tuple[dict, GameResult]], Optional[GameResult]]:
    rnd = _active_round(bracket)
    if rnd is None:
        return [], None
    results: List[Tuple[dict, GameResult]] = []
    user_result = None
    uid = world.user_team_id
    for m in rnd:
        if m["winner"] is not None:
            continue
        home, away = m["a"], m["b"]              # higher seed hosts
        is_user = uid in (home, away)
        g = Game(gid=world.new_gid(), day=world.day, home=home, away=away, is_playoff=True)
        world.schedule.append(g)
        res = sim_one(world, g, is_playoff=True, collect_pbp=watch_user and is_user)
        m["gid"] = g.gid
        m["a_score"], m["b_score"] = res.home_score, res.away_score
        m["winner"] = home if res.home_score > res.away_score else away
        results.append((m, res))
        if is_user:
            user_result = res
    _advance_bracket(bracket)
    return results, user_result


def advance_college_slate(world: World, *, watch_user: bool = False
                          ) -> Tuple[List[Tuple[dict, GameResult]], Optional[GameResult]]:
    b = world.bracket
    if b["stage"] == "conf":
        results: List[Tuple[dict, GameResult]] = []
        user_result = None
        for cb in b["conf"].values():
            if cb["champion"] is None:
                r, ur = _play_round_slate(world, cb, watch_user)
                results += r
                user_result = ur or user_result
        if all(cb["champion"] is not None for cb in b["conf"].values()):
            _build_national_field(world)
            b["stage"] = "national"
        return results, user_result
    if b["stage"] == "national":
        r, ur = _play_round_slate(world, b["national"], watch_user)
        if b["national"]["champion"] is not None:
            b["champion"] = b["national"]["champion"]
            b["stage"] = "done"
            world.phase = Phase.DRAFT
        return r, ur
    return [], None


def college_postseason_complete(world: World) -> bool:
    return bool(world.bracket) and world.bracket.get("champion") is not None


def national_champion(world: World) -> Optional[int]:
    return world.bracket.get("champion") if world.bracket else None


def user_still_alive(world: World) -> bool:
    """Whether the user's team is still in the bracket (not yet eliminated)."""
    b = world.bracket
    uid = world.user_team_id
    if not b or uid is None:
        return False
    brackets = list(b.get("conf", {}).values())
    if b.get("national"):
        brackets.append(b["national"])
    for br in brackets:
        for rnd in br["rounds"]:
            for m in rnd:
                if uid in (m["a"], m["b"]) and m["winner"] is not None and m["winner"] != uid:
                    return False
    return True
