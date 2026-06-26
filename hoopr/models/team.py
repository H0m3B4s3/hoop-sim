"""The Team model plus roster/lineup helper functions.

Team stores player *ids* only (the authoritative Player objects live on the World). Helpers
that need player data take a ``players`` mapping so the model stays pure data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from hoopr.config import DEFAULT_OWNER_BUDGET, STARTERS, game_minutes
from hoopr.models.attributes import POSITIONS
from hoopr.models.player import Player
from hoopr.models.stats import StatLine
from hoopr.models.tactics import Tactics


@dataclass
class Team:
    tid: int
    city: str
    name: str
    abbrev: str
    conference: str
    division: str = ""
    color: str = "white"

    roster: List[int] = field(default_factory=list)        # ordered player ids
    starters: List[int] = field(default_factory=list)      # up to 5 player ids
    minutes_target: Dict[int, int] = field(default_factory=dict)  # pid -> target minutes
    auto_lineup: bool = True                               # False -> user set the starting five
    tactics: Tactics = field(default_factory=Tactics)

    wins: int = 0
    losses: int = 0
    conf_wins: int = 0
    conf_losses: int = 0
    points_for: int = 0
    points_against: int = 0
    streak: int = 0                                        # + win streak / - losing streak

    market_size: int = 3                                   # 1 (small) .. 5 (large)
    owner_budget: int = DEFAULT_OWNER_BUDGET
    mle_used: bool = False                                  # mid-level exception spent this offseason

    # League membership and college-mode state.
    league: str = "nba"                                    # "nba" | "college"
    prestige: int = 3                                      # 1 (mid-major) .. 5 (blue blood)
    nil_budget: int = 0                                    # annual NIL collective funds (college)

    season_stats: StatLine = field(default_factory=StatLine)

    # -- identity -----------------------------------------------------------
    @property
    def full_name(self) -> str:
        return f"{self.city} {self.name}"

    @property
    def games_played(self) -> int:
        return self.wins + self.losses

    @property
    def win_pct(self) -> float:
        gp = self.games_played
        return self.wins / gp if gp else 0.0

    @property
    def point_diff(self) -> int:
        return self.points_for - self.points_against

    @property
    def record_str(self) -> str:
        return f"{self.wins}-{self.losses}"

    @property
    def streak_str(self) -> str:
        if self.streak == 0:
            return "-"
        return f"{'W' if self.streak > 0 else 'L'}{abs(self.streak)}"

    # -- membership ---------------------------------------------------------
    def add_player(self, pid: int) -> None:
        if pid not in self.roster:
            self.roster.append(pid)

    def remove_player(self, pid: int) -> None:
        if pid in self.roster:
            self.roster.remove(pid)
        if pid in self.starters:
            self.starters.remove(pid)
        self.minutes_target.pop(pid, None)

    # -- results ------------------------------------------------------------
    def record_result(self, won: bool, pf: int, pa: int, conference_game: bool) -> None:
        if won:
            self.wins += 1
            self.streak = self.streak + 1 if self.streak >= 0 else 1
            if conference_game:
                self.conf_wins += 1
        else:
            self.losses += 1
            self.streak = self.streak - 1 if self.streak <= 0 else -1
            if conference_game:
                self.conf_losses += 1
        self.points_for += pf
        self.points_against += pa

    def reset_record(self) -> None:
        self.wins = self.losses = 0
        self.conf_wins = self.conf_losses = 0
        self.points_for = self.points_against = 0
        self.streak = 0
        self.season_stats.reset()

    # -- serialization ------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "tid": self.tid,
            "city": self.city,
            "name": self.name,
            "abbrev": self.abbrev,
            "conference": self.conference,
            "division": self.division,
            "color": self.color,
            "roster": list(self.roster),
            "starters": list(self.starters),
            "minutes_target": {str(k): v for k, v in self.minutes_target.items()},
            "auto_lineup": self.auto_lineup,
            "tactics": self.tactics.to_dict(),
            "wins": self.wins,
            "losses": self.losses,
            "conf_wins": self.conf_wins,
            "conf_losses": self.conf_losses,
            "points_for": self.points_for,
            "points_against": self.points_against,
            "streak": self.streak,
            "market_size": self.market_size,
            "owner_budget": self.owner_budget,
            "mle_used": self.mle_used,
            "league": self.league,
            "prestige": self.prestige,
            "nil_budget": self.nil_budget,
            "season_stats": self.season_stats.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Team":
        return cls(
            tid=d["tid"],
            city=d["city"],
            name=d["name"],
            abbrev=d["abbrev"],
            conference=d["conference"],
            division=d.get("division", ""),
            color=d.get("color", "white"),
            roster=list(d.get("roster", [])),
            starters=list(d.get("starters", [])),
            minutes_target={int(k): v for k, v in d.get("minutes_target", {}).items()},
            auto_lineup=d.get("auto_lineup", True),
            tactics=Tactics.from_dict(d.get("tactics", {})),
            wins=d.get("wins", 0),
            losses=d.get("losses", 0),
            conf_wins=d.get("conf_wins", 0),
            conf_losses=d.get("conf_losses", 0),
            points_for=d.get("points_for", 0),
            points_against=d.get("points_against", 0),
            streak=d.get("streak", 0),
            market_size=d.get("market_size", 3),
            owner_budget=d.get("owner_budget", DEFAULT_OWNER_BUDGET),
            mle_used=d.get("mle_used", False),
            league=d.get("league", "nba"),
            prestige=d.get("prestige", 3),
            nil_budget=d.get("nil_budget", 0),
            season_stats=StatLine.from_dict(d.get("season_stats", {})),
        )


# ---------------------------------------------------------------------------
# Roster / lineup helpers (operate on a players mapping)
# ---------------------------------------------------------------------------
def roster_players(team: Team, players: Dict[int, Player]) -> List[Player]:
    return [players[pid] for pid in team.roster if pid in players]


def team_salary(team: Team, players: Dict[int, Player]) -> int:
    return sum(players[pid].contract.current_salary for pid in team.roster if pid in players)


def available_players(team: Team, players: Dict[int, Player]) -> List[Player]:
    return [p for p in roster_players(team, players) if p.available]


_POSITION_INDEX = {pos: i for i, pos in enumerate(POSITIONS)}


def position_distance(player: Player, slot: str) -> float:
    """How far out of position a player is for a slot (0 = natural, smaller is better)."""
    if player.position == slot:
        return 0.0
    if player.secondary_position == slot:
        return 0.4
    return float(abs(_POSITION_INDEX[player.position] - _POSITION_INDEX[slot]))


def assign_positions(five: List[Player]) -> List[int]:
    """Slot up to five players into PG..C, minimizing how far each plays out of position.

    Positions are flexible: a shooting guard will start at point guard if that is the best fit,
    rather than benching a better player to force a natural point guard into the lineup.
    """
    remaining = list(five)
    ordered: List[int] = []
    for slot in POSITIONS:
        if not remaining:
            break
        best = min(remaining, key=lambda p: (position_distance(p, slot), -p.overall))
        ordered.append(best.pid)
        remaining.remove(best)
    return ordered


def auto_set_lineup(team: Team, players: Dict[int, Player]) -> None:
    """Set the starting five and rotation minutes.

    With ``auto_lineup`` on, the five best available players start (slotted into positions by
    fit). If the user has set a manual lineup, that five is kept and only unavailable players are
    replaced.
    """
    pool = available_players(team, players)
    if not pool:
        pool = roster_players(team, players)       # everyone hurt; still field a lineup

    if not team.auto_lineup and team.starters:
        available_ids = {p.pid for p in pool}
        kept = [pid for pid in team.starters if pid in available_ids]
        bench = sorted((p for p in pool if p.pid not in kept),
                       key=lambda p: p.overall, reverse=True)
        while len(kept) < STARTERS and bench:
            kept.append(bench.pop(0).pid)
        team.starters = kept
    else:
        best_five = sorted(pool, key=lambda p: p.overall, reverse=True)[:STARTERS]
        team.starters = assign_positions(best_five)
    set_auto_minutes(team, players)


def set_auto_minutes(team: Team, players: Dict[int, Player]) -> None:
    """Distribute 240 player-minutes across healthy players, weighted by overall.

    Starters get a floor; depth beyond ~10 players gets none. Targets are advisory — the
    engine still adjusts for in-game fatigue and foul trouble.
    """
    pool = available_players(team, players)
    if not pool:
        team.minutes_target = {}
        return
    pool.sort(key=lambda p: (p.pid in team.starters, p.overall), reverse=True)
    rotation = pool[:10]
    weights = [max(1.0, p.overall - 55) ** 1.4 for p in rotation]
    total_w = sum(weights)
    minutes = game_minutes(team.league)            # 48 (NBA) or 40 (college)
    total_minutes = STARTERS * minutes
    starter_floor = minutes // 2
    cap = minutes - 10
    targets: Dict[int, int] = {}
    for p, w in zip(rotation, weights):
        share = total_minutes * (w / total_w)
        floor = starter_floor if p.pid in team.starters else 0
        targets[p.pid] = int(max(floor, min(cap, round(share))))
    # Spread any leftover/excess minutes across the rotation, never exceeding the per-player cap.
    drift = total_minutes - sum(targets.values())
    step = 1 if drift > 0 else -1
    guard = 0
    while drift != 0 and rotation and guard < 2000:
        for p in rotation:
            if drift == 0:
                break
            floor = starter_floor if p.pid in team.starters else 0
            new_val = targets[p.pid] + step
            if floor <= new_val <= cap:
                targets[p.pid] = new_val
                drift -= step
        guard += 1
    team.minutes_target = targets
