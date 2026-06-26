"""Regular-season orchestration: scheduling, result application, and day advancement."""
from __future__ import annotations

import datetime
from typing import List, Optional, Tuple

from hoopr.config import SEASON_START_DAY, SEASON_START_MONTH
from hoopr.models.league import Game, Phase
from hoopr.models.player import Injury
from hoopr.models.team import auto_set_lineup
from hoopr.models.world import World
from hoopr.sim.boxscore import GameResult
from hoopr.sim.engine import simulate_game

DayResults = List[Tuple[Game, GameResult]]


# ---------------------------------------------------------------------------
# Scheduling (circle method: every team plays exactly once per round/day)
# ---------------------------------------------------------------------------
def generate_schedule(world: World) -> None:
    world.schedule = [g for g in world.schedule if g.is_playoff]   # clear regular games
    tids = sorted(world.teams.keys())
    n = len(tids)
    fixed, rot = tids[0], tids[1:]
    rounds = world.season_games
    for r in range(rounds):
        arrangement = [fixed] + rot
        for i in range(n // 2):
            x, y = arrangement[i], arrangement[n - 1 - i]
            # alternate home/away for balance
            home, away = (x, y) if (r + i) % 2 == 0 else (y, x)
            world.schedule.append(Game(gid=world.new_gid(), day=r, home=home, away=away))
        rot = [rot[-1]] + rot[:-1]


def game_date(world: World, day: int) -> str:
    base = datetime.date(world.season_year, SEASON_START_MONTH, SEASON_START_DAY)
    return (base + datetime.timedelta(days=day * 2)).strftime("%a %b %d, %Y")


# ---------------------------------------------------------------------------
# Result application
# ---------------------------------------------------------------------------
def _apply_result(world: World, game: Game, result: GameResult, is_playoff: bool) -> None:
    game.home_score = result.home_score
    game.away_score = result.away_score
    game.played = True

    home, away = world.teams[game.home], world.teams[game.away]
    for team, roster in ((home, home.roster), (away, away.roster)):
        bucket_target = "playoffs" if is_playoff else "season"
        for pid in roster:
            if pid in result.box:
                getattr(world.players[pid], bucket_target).add(result.box[pid])
        if not is_playoff:
            team.season_stats.add(result.team_line(list(roster)))

    if not is_playoff:
        conf_game = home.conference == away.conference
        home_won = result.home_score > result.away_score
        home.record_result(home_won, result.home_score, result.away_score, conf_game)
        away.record_result(not home_won, result.away_score, result.home_score, conf_game)

    for pid, games, desc, severity in result.injuries:
        player = world.players[pid]
        if player.injury is None or games > player.injury.games_remaining:
            player.injury = Injury(desc, games, severity)


def sim_one(world: World, game: Game, *, collect_pbp: bool = False,
            is_playoff: bool = False) -> GameResult:
    """Simulate and apply a single scheduled game."""
    home, away = world.teams[game.home], world.teams[game.away]
    # Make sure lineups reflect the current healthy roster.
    auto_set_lineup(home, world.players)
    auto_set_lineup(away, world.players)
    result = simulate_game(world, home, away, collect_pbp=collect_pbp)
    _apply_result(world, game, result, is_playoff)
    return result


def _heal_injuries(world: World) -> None:
    for p in world.players.values():
        if p.injury is not None:
            p.injury.games_remaining -= 1
            if p.injury.games_remaining <= 0:
                p.injury = None


# ---------------------------------------------------------------------------
# Day advancement
# ---------------------------------------------------------------------------
def games_on_day(world: World, day: int) -> List[Game]:
    return [g for g in world.schedule
            if g.day == day and not g.is_playoff and not g.played]


def regular_season_complete(world: World) -> bool:
    return all(g.played for g in world.schedule if not g.is_playoff)


def last_regular_day(world: World) -> int:
    days = [g.day for g in world.schedule if not g.is_playoff]
    return max(days) if days else -1


def user_next_game(world: World) -> Optional[Game]:
    uid = world.user_team_id
    pending = [g for g in world.schedule
               if not g.is_playoff and not g.played and g.involves(uid)]
    return min(pending, key=lambda g: g.day) if pending else None


def advance_one_day(world: World, *, watch_user: bool = False) -> Tuple[DayResults, Optional[GameResult]]:
    """Simulate every unplayed regular-season game on the current day, then heal + advance."""
    day = world.day
    todays = games_on_day(world, day)
    results: DayResults = []
    user_result: Optional[GameResult] = None
    uid = world.user_team_id
    for g in todays:
        is_user = uid is not None and g.involves(uid)
        res = sim_one(world, g, collect_pbp=watch_user and is_user)
        results.append((g, res))
        if is_user:
            user_result = res
    _heal_injuries(world)
    world.day += 1
    return results, user_result


def start_season(world: World) -> None:
    """Reset records/stats and build a fresh schedule for a new regular season."""
    for team in world.teams.values():
        team.reset_record()
    for p in world.players.values():
        p.season.reset()
        p.injury = None
        p.condition = 100.0
    generate_schedule(world)
    world.bracket = None
    world.day = 0
    world.phase = Phase.REGULAR_SEASON
