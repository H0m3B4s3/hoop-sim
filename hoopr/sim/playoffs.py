"""Playoff bracket: seeding, play-in, best-of-7 series, and round advancement.

Bracket state is stored on ``world.bracket`` as a JSON-native dict so it serializes with the
save. Series are advanced one game at a time ("slates") so the user can watch their own games.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from hoopr.config import CONFERENCES
from hoopr.models.league import Game, Phase, conference_standings
from hoopr.models.world import World
from hoopr.sim.boxscore import GameResult
from hoopr.sim.season import sim_one

BEST_OF = 7
WINS_NEEDED = BEST_OF // 2 + 1            # 4
HIGH_SEED_HOME_GAMES = {1, 2, 5, 7}      # 2-2-1-1-1 format

ROUND_LABELS = {"R1": "First Round", "R2": "Conference Semifinals",
                "CF": "Conference Finals", "Finals": "Finals", "done": "Complete"}
NEXT_ROUND = {"R1": "R2", "R2": "CF", "CF": "Finals", "Finals": "done"}


def _new_series(world: World, hi: int, lo: int, conf: str, rnd: str) -> dict:
    return {"sid": f"{rnd}-{hi}-{lo}", "conf": conf, "round": rnd,
            "hi": hi, "lo": lo, "hi_w": 0, "lo_w": 0, "winner": None, "games": []}


def _abbr(world: World, tid: int) -> str:
    return world.teams[tid].abbrev


# ---------------------------------------------------------------------------
# Start of playoffs: seeding + play-in
# ---------------------------------------------------------------------------
def start_playoffs(world: World) -> List[str]:
    seeds: Dict[int, int] = {}
    log: List[str] = []
    series: List[dict] = []

    for conf in CONFERENCES:
        order = conference_standings(world.team_list(), conf)
        top6 = order[:6]
        playin = order[6:10]
        for i, t in enumerate(top6, start=1):
            seeds[t.tid] = i
        seven, eight = _resolve_play_in(world, conf, playin, log)
        seeds[seven] = 7
        seeds[eight] = 8

        ordered = top6 + [world.teams[seven], world.teams[eight]]
        s = [t.tid for t in ordered]            # index 0->seed1 .. index7->seed8
        # 1v8, 4v5, 3v6, 2v7  (gives a standard bracket)
        for hi_idx, lo_idx in ((0, 7), (3, 4), (2, 5), (1, 6)):
            series.append(_new_series(world, s[hi_idx], s[lo_idx], conf, "R1"))

    world.bracket = {"round": "R1", "series": series, "all_series": list(series),
                     "seeds": {str(k): v for k, v in seeds.items()},
                     "champion": None, "log": log}
    world.phase = Phase.PLAYOFFS
    return log


def _resolve_play_in(world: World, conf: str, teams, log: List[str]) -> Tuple[int, int]:
    """Auto-resolve the 7-10 play-in; return (7th seed tid, 8th seed tid)."""
    if len(teams) < 4:
        # short league fallback: just take the next two by record
        return teams[0].tid, teams[1].tid
    t7, t8, t9, t10 = teams[0], teams[1], teams[2], teams[3]
    a_winner, a_loser = _play_in_game(world, t7, t8, log, conf, "7/8")
    b_winner, _ = _play_in_game(world, t9, t10, log, conf, "9/10")
    seven = a_winner
    eight, _ = _play_in_game(world, world.teams[a_loser], world.teams[b_winner],
                             log, conf, "8th seed")
    return seven, eight


def _play_in_game(world: World, home, away, log: List[str], conf: str, label: str):
    g = Game(gid=world.new_gid(), day=world.day, home=home.tid, away=away.tid, is_playoff=True)
    world.schedule.append(g)
    res = sim_one(world, g, is_playoff=True)
    win = g.home if res.home_score > res.away_score else g.away
    lose = g.away if win == g.home else g.home
    log.append(f"[{conf} {label}] {away.abbrev} {res.away_score} @ "
               f"{home.abbrev} {res.home_score} → {world.teams[win].abbrev} advances")
    return win, lose


# ---------------------------------------------------------------------------
# Slate advancement
# ---------------------------------------------------------------------------
def active_series(world: World) -> List[dict]:
    if not world.bracket:
        return []
    return [s for s in world.bracket["series"] if s["winner"] is None]


def series_status(world: World, s: dict) -> str:
    hi, lo = _abbr(world, s["hi"]), _abbr(world, s["lo"])
    return f"{hi} {s['hi_w']}-{s['lo_w']} {lo}"


def _series_next_home_away(s: dict) -> Tuple[int, int]:
    game_no = s["hi_w"] + s["lo_w"] + 1
    if game_no in HIGH_SEED_HOME_GAMES:
        return s["hi"], s["lo"]
    return s["lo"], s["hi"]


def advance_playoff_slate(world: World, *, watch_user: bool = False
                          ) -> Tuple[List[Tuple[dict, GameResult]], Optional[GameResult]]:
    """Play the next game of every undecided series in the current round."""
    results: List[Tuple[dict, GameResult]] = []
    user_result: Optional[GameResult] = None
    uid = world.user_team_id
    for s in active_series(world):
        home, away = _series_next_home_away(s)
        is_user = uid is not None and uid in (home, away)
        g = Game(gid=world.new_gid(), day=world.day, home=home, away=away, is_playoff=True,
                 series_id=s["sid"])
        world.schedule.append(g)
        res = sim_one(world, g, is_playoff=True, collect_pbp=watch_user and is_user)
        s["games"].append(g.gid)
        if res.home_score > res.away_score:
            winner = home
        else:
            winner = away
        if winner == s["hi"]:
            s["hi_w"] += 1
        else:
            s["lo_w"] += 1
        if s["hi_w"] >= WINS_NEEDED:
            s["winner"] = s["hi"]
        elif s["lo_w"] >= WINS_NEEDED:
            s["winner"] = s["lo"]
        results.append((s, res))
        if is_user:
            user_result = res

    if not active_series(world):
        _build_next_round(world)
    return results, user_result


def _seed(world: World, tid: int) -> int:
    return world.bracket["seeds"].get(str(tid), 99)


def _build_next_round(world: World) -> None:
    bracket = world.bracket
    current = bracket["round"]
    nxt = NEXT_ROUND[current]
    finished = [s for s in bracket["series"] if s["round"] == current]

    if nxt == "done":
        champ = finished[0]["winner"]
        bracket["champion"] = champ
        bracket["round"] = "done"
        bracket["series"] = []
        world.phase = Phase.DRAFT
        return

    new_series: List[dict] = []
    if nxt == "Finals":
        champs = {s["conf"]: s["winner"] for s in finished}
        a, b = champs[CONFERENCES[0]], champs[CONFERENCES[1]]
        hi, lo = (a, b) if world.teams[a].win_pct >= world.teams[b].win_pct else (b, a)
        new_series.append(_new_series(world, hi, lo, "Finals", "Finals"))
    else:
        for conf in CONFERENCES:
            conf_series = [s for s in finished if s["conf"] == conf]
            winners = [s["winner"] for s in conf_series]
            # pair consecutive winners (bracket order preserved)
            for i in range(0, len(winners), 2):
                a, b = winners[i], winners[i + 1]
                hi, lo = (a, b) if _seed(world, a) <= _seed(world, b) else (b, a)
                new_series.append(_new_series(world, hi, lo, conf, nxt))

    bracket["round"] = nxt
    bracket["series"] = new_series
    bracket["all_series"].extend(new_series)


def playoffs_complete(world: World) -> bool:
    return bool(world.bracket) and world.bracket.get("champion") is not None


def champion(world: World) -> Optional[int]:
    return world.bracket.get("champion") if world.bracket else None
