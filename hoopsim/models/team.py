"""The Team model plus roster/lineup helper functions.

Team stores player *ids* only (the authoritative Player objects live on the World). Helpers
that need player data take a ``players`` mapping so the model stays pure data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from hoopsim.config import DEFAULT_OWNER_BUDGET, STARTERS, game_minutes
from hoopsim.models.attributes import POSITIONS
from hoopsim.models.coach import Coach, profile_for
from hoopsim.models.player import Player
from hoopsim.models.stats import StatLine
from hoopsim.models.tactics import Tactics


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
    block_list: List[int] = field(default_factory=list)    # pids the GM has made available
    minutes_target: Dict[int, int] = field(default_factory=dict)  # pid -> target minutes
    auto_lineup: bool = True                               # False -> user set the starting five
    rotation: List[int] = field(default_factory=list)      # user-pinned rotation beyond the starters; [] -> automatic
    roles: Dict[str, int] = field(default_factory=dict)    # role tag -> pid (one player per role); see ROLE_TAGS
    chemistry: Dict[str, float] = field(default_factory=dict)  # "lo,hi" pid pair -> shared on-court seconds
    tactics: Tactics = field(default_factory=Tactics)
    coach: Optional[Coach] = None                          # head coach (rotation/tactics identity)

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
    dead_money: List[int] = field(default_factory=list)    # waived guaranteed salary, per season (idx 0 = now)

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
        if pid in self.rotation:
            self.rotation.remove(pid)
        for role, holder in list(self.roles.items()):
            if holder == pid:
                del self.roles[role]
        self.minutes_target.pop(pid, None)
        # Chemistry travels with the pairing: a departing player takes his shared history with him.
        self.chemistry = {k: v for k, v in self.chemistry.items()
                          if pid not in _pair_pids(k)}

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
            "block_list": list(self.block_list),
            "minutes_target": {str(k): v for k, v in self.minutes_target.items()},
            "auto_lineup": self.auto_lineup,
            "rotation": list(self.rotation),
            "roles": {k: v for k, v in self.roles.items()},
            "chemistry": {k: round(v, 1) for k, v in self.chemistry.items()},
            "tactics": self.tactics.to_dict(),
            "coach": self.coach.to_dict() if self.coach else None,
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
            "dead_money": list(self.dead_money),
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
            block_list=list(d.get("block_list", [])),
            minutes_target={int(k): v for k, v in d.get("minutes_target", {}).items()},
            auto_lineup=d.get("auto_lineup", True),
            rotation=list(d.get("rotation", [])),
            roles={k: int(v) for k, v in d.get("roles", {}).items()},
            chemistry={k: float(v) for k, v in d.get("chemistry", {}).items()},
            tactics=Tactics.from_dict(d.get("tactics", {})),
            coach=Coach.from_dict(d["coach"]) if d.get("coach") else None,
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
            dead_money=list(d.get("dead_money", [])),
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


def dead_cap(team: Team) -> int:
    """This season's dead money — guaranteed salary still owed to waived players."""
    return team.dead_money[0] if team.dead_money else 0


def team_salary(team: Team, players: Dict[int, Player]) -> int:
    """Payroll counting toward the cap: active contracts plus this year's dead money."""
    active = sum(players[pid].contract.current_salary for pid in team.roster if pid in players)
    return active + dead_cap(team)


def available_players(team: Team, players: Dict[int, Player]) -> List[Player]:
    return [p for p in roster_players(team, players) if p.available]


# ---------------------------------------------------------------------------
# Chemistry (lineup familiarity)
# ---------------------------------------------------------------------------
def pair_key(a: int, b: int) -> str:
    """Order-independent key for a pair of player ids in ``team.chemistry``."""
    return f"{a},{b}" if a < b else f"{b},{a}"


def _pair_pids(key: str) -> tuple:
    lo, hi = key.split(",")
    return int(lo), int(hi)


def lineup_familiarity_secs(chemistry: Dict[str, float], five: List[int]) -> float:
    """Average shared on-court seconds across the pairs of a lineup (a missing pair counts as 0).

    Averaging (rather than taking the minimum) means slotting one new face into a settled five
    dents chemistry partway and recovers as he logs minutes, instead of dropping the whole unit to
    the floor.
    """
    if len(five) < 2:
        return 0.0
    pairs = [(five[i], five[j]) for i in range(len(five)) for j in range(i + 1, len(five))]
    total = sum(chemistry.get(pair_key(a, b), 0.0) for a, b in pairs)
    return total / len(pairs)


def seed_chemistry(team: Team, secs: float) -> None:
    """Seed every current roster pair to ``secs`` shared time (an established, gelled roster).

    Called at world creation so a league that has "already existed" plays at full chemistry from
    the opening tip; players who arrive later start cold.
    """
    roster = team.roster
    for i in range(len(roster)):
        for j in range(i + 1, len(roster)):
            team.chemistry[pair_key(roster[i], roster[j])] = secs


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


# Cap how deep a user can spread minutes so a pinned rotation stays meaningful (not a 15-man mob).
MAX_ROTATION = 12       # starters + pinned reserves

# Role tags bias the rotation/closing math. Each tag belongs to at most one player on a team
# (``team.roles`` maps tag -> pid); a player may hold more than one. The engine reads them:
#   sixth_man     -> jumps the bench queue (first reserve off the bench, most reserve minutes)
#   defensive_ace -> earns extra minutes against strong offenses
#   closer        -> overrides crunch-time lineup selection (on the floor to close, if able)
ROLE_TAGS = ("sixth_man", "defensive_ace", "closer")
ROLE_LABELS = {"sixth_man": "Sixth Man", "defensive_ace": "Defensive Ace", "closer": "Closer"}
# How hard the sixth man's minutes weight is boosted so he tops the bench queue.
SIXTH_MAN_WEIGHT_BOOST = 1.6


def role_pid(team: Team, role: str, players: Dict[int, Player]) -> Optional[int]:
    """The pid tagged with ``role`` if they're on the roster and available, else None."""
    pid = team.roles.get(role)
    if pid is None or pid not in team.roster:
        return None
    p = players.get(pid)
    return pid if p is not None and p.available else None


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


def rotation_pool(team: Team, players: Dict[int, Player]) -> List[Player]:
    """The available players who should draw minutes, best-first (starters lead).

    With a user-pinned ``team.rotation`` the membership is the user's call — starters plus the
    pinned players, and nobody else — so a coach can hand a raw rookie real run over a higher-rated
    veteran parked at the end of the bench, even if that means a deliberately short rotation. The
    only override is an injury safety net: if availability drops the pinned group below a fieldable
    five, the next-best players backfill so a lineup can still take the floor. With no manual
    rotation we fall back to the head coach's automatic shape (top ``rotation_size`` by overall).
    """
    pool = available_players(team, players)
    if not pool:
        return []
    prof = profile_for(team)                       # rotation shape comes from the head coach
    pool.sort(key=lambda p: (p.pid in team.starters, p.overall), reverse=True)
    sixth = role_pid(team, "sixth_man", players)   # a tagged sixth man always draws minutes
    if not team.rotation:
        chosen = pool[:prof.rotation_size]
        if sixth is not None and all(p.pid != sixth for p in chosen):
            chosen = chosen + [p for p in pool if p.pid == sixth]
        return chosen
    pinned = set(team.starters) | set(team.rotation)
    if sixth is not None:
        pinned.add(sixth)
    chosen = [p for p in pool if p.pid in pinned]
    if len(chosen) < STARTERS:                      # injuries gutted the rotation; backfill to a five
        for p in pool:
            if p.pid not in pinned:
                chosen.append(p)
                if len(chosen) >= STARTERS:
                    break
    return chosen


def set_auto_minutes(team: Team, players: Dict[int, Player]) -> None:
    """Distribute 240 player-minutes across the rotation, weighted by overall.

    Starters get a floor; players outside the rotation get none. Targets are advisory — the
    engine still adjusts for in-game fatigue and foul trouble.
    """
    pool = available_players(team, players)
    if not pool:
        team.minutes_target = {}
        return
    prof = profile_for(team)                       # rotation shape comes from the head coach
    rotation = rotation_pool(team, players)
    weights = [max(1.0, p.overall - 55) ** prof.star_reliance for p in rotation]
    sixth = role_pid(team, "sixth_man", players)   # boost so he tops the bench queue
    if sixth is not None:
        for i, p in enumerate(rotation):
            if p.pid == sixth and p.pid not in team.starters:
                weights[i] *= SIXTH_MAN_WEIGHT_BOOST
    total_w = sum(weights)
    minutes = game_minutes(team.league)            # 48 (NBA) or 40 (college)
    total_minutes = STARTERS * minutes
    starter_floor = minutes // 2 + prof.floor_bonus
    cap = minutes - prof.cap_slack
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
