"""Advanced/derived stats (TS%, usage%, offensive/defensive rating) built on top of StatLine.

These take pairs of :class:`~hoopsim.models.stats.StatLine` (a team and its opponent, or a
player and their team) and work identically whether the inputs are a single game's box or a
season aggregate. Individual-player ORtg/DRtg are a simplified proxy -- the sim doesn't track
play-by-play assist/shot-creation attribution needed for a true Dean Oliver individual rating,
so a player's rating scales the team's rating by their relative efficiency. All functions guard
division by zero and return 0.0 rather than raising, since "no data yet" is a normal state
(a fresh season, a DNP, an empty opponent StatLine).
"""
from __future__ import annotations

from hoopsim.models.stats import StatLine


def _est_possessions(s: StatLine) -> float:
    return s.fga - s.oreb + s.tov + 0.44 * s.fta


def possessions(team: StatLine, opp: StatLine) -> float:
    """Estimated possessions, averaging both sides' estimates per standard NBA convention."""
    own = _est_possessions(team)
    if opp.fga == 0 and opp.fta == 0 and opp.tov == 0 and opp.oreb == 0:
        return max(own, 0.0)
    return max(0.5 * (own + _est_possessions(opp)), 0.0)


def _rating(scoring_pts: float, poss: float) -> float:
    return 100.0 * scoring_pts / poss if poss > 0 else 0.0


def team_ortg(team: StatLine, opp: StatLine) -> float:
    return _rating(team.pts, possessions(team, opp))


def team_drtg(team: StatLine, opp: StatLine) -> float:
    return _rating(opp.pts, possessions(team, opp))


def pace(team: StatLine, opp: StatLine) -> float:
    """Estimated possessions per 48 minutes of team play.

    ``team.minutes`` sums every player's on-court minutes (five players on the floor at once),
    so ``team.minutes / 5`` is the actual team-minutes played -- one game or a whole season,
    with no dependence on ``StatLine.gp`` (which counts player-games, not team-games).
    """
    team_minutes = team.minutes / 5.0
    if team_minutes <= 0:
        return 0.0
    return possessions(team, opp) / team_minutes * 48.0


def usage_pct(player: StatLine, team: StatLine) -> float:
    """Standard usage rate: share of team possessions used by the player while on the floor."""
    if player.minutes <= 0:
        return 0.0
    team_denom = team.fga + 0.44 * team.fta + team.tov
    if team_denom <= 0:
        return 0.0
    player_num = (player.fga + 0.44 * player.fta + player.tov) * (team.minutes / 5.0)
    return 100.0 * player_num / (player.minutes * team_denom)


def player_ortg_proxy(player: StatLine, team: StatLine, opp: StatLine) -> float:
    """Team ORtg scaled by the player's shooting efficiency relative to the team's."""
    base = team_ortg(team, opp)
    if team.ts_pct <= 0 or (player.fga + player.fta) <= 0:
        return base
    return base * (player.ts_pct / team.ts_pct)


def player_drtg_proxy(player: StatLine, team: StatLine, opp: StatLine) -> float:
    """Team DRtg scaled inversely by the player's defensive-activity rate vs. the team's.

    Lower DRtg is better defense, so a player generating more stocks/rebounds per minute than
    the team average pulls their DRtg below the team's; less activity pushes it above.
    """
    base = team_drtg(team, opp)
    if player.minutes <= 0 or team.minutes <= 0:
        return base
    team_rate = (team.stl + team.blk + team.dreb) / team.minutes
    if team_rate <= 0:
        return base
    player_rate = (player.stl + player.blk + player.dreb) / player.minutes
    factor = max(0.5, min(2.0, 2.0 - player_rate / team_rate))
    return base * factor
