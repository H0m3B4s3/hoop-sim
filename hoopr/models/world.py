"""The World — root aggregate holding all game state and the save target.

Players live in a single ``players`` map keyed by id; teams reference players by id only. This
keeps trades/signings to simple reassignments and avoids duplicated state. The RNG state is part
of the world so a reloaded save reproduces simulations exactly.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from hoopr.config import (DEFAULT_COLLEGE_ECONOMY, FIRST_APRON, LUXURY_TAX_LINE, SALARY_CAP,
                          SCHEMA_VERSION)
from hoopr.models.contract import Contract
from hoopr.models.draft import DraftClass, DraftPick
from hoopr.models.league import Game, Phase
from hoopr.models.player import Player
from hoopr.models.team import Team
from hoopr.rng import Rng


class World:
    def __init__(self, rng: Optional[Rng] = None) -> None:
        self.rng: Rng = rng or Rng()
        self.season_year: int = 2025
        self.phase: str = Phase.PRESEASON
        self.day: int = 0

        self.teams: Dict[int, Team] = {}
        self.players: Dict[int, Player] = {}
        self.schedule: List[Game] = []
        self.free_agents: List[int] = []
        self.draft_class: Optional[DraftClass] = None
        self.draft_picks: List[DraftPick] = []       # tradeable future picks (NBA)
        self.trade_offers: List[dict] = []           # pending AI-initiated offers to the user
        self.offer_cooldowns: Dict[int, int] = {}    # pid -> earliest day a new offer may spawn
        self.bracket: Optional[dict] = None          # JSON-native playoff state

        self.user_team_id: Optional[int] = None
        self.season_games: int = 82
        # Live salary-cap values (grow each NBA offseason; start from config defaults).
        self.salary_cap: int = SALARY_CAP
        self.luxury_tax_line: int = LUXURY_TAX_LINE
        self.first_apron: int = FIRST_APRON
        self.history: List[dict] = []                # champions / awards per finished season

        # Mode & the college layer. ``mode`` is the league the user controls; ``other_teams``
        # holds the *other* league (the pipeline partner) as Team objects (their players live in
        # the shared ``players`` map). ``recruits`` are unsigned high-school prospect pids.
        self.mode: str = "nba"                       # "nba" | "college"
        self.college_economy: str = DEFAULT_COLLEGE_ECONOMY   # "scholarship" | "nil"
        self.other_teams: Dict[int, Team] = {}
        self.recruits: List[int] = []
        self.pipeline: Optional[dict] = None         # JSON-native college->NBA draft results

        self._next_pid: int = 1
        self._next_gid: int = 1
        self._next_offer_id: int = 1

    # -- id allocation ------------------------------------------------------
    def new_pid(self) -> int:
        pid = self._next_pid
        self._next_pid += 1
        return pid

    def new_gid(self) -> int:
        gid = self._next_gid
        self._next_gid += 1
        return gid

    def new_offer_id(self) -> int:
        oid = self._next_offer_id
        self._next_offer_id += 1
        return oid

    # -- accessors ----------------------------------------------------------
    @property
    def user_team(self) -> Optional[Team]:
        if self.user_team_id is None:
            return None
        return self.teams.get(self.user_team_id)

    def team(self, tid: int) -> Team:
        return self.teams[tid]

    def player(self, pid: int) -> Player:
        return self.players[pid]

    def team_list(self) -> List[Team]:
        return list(self.teams.values())

    def other_team_list(self) -> List[Team]:
        return list(self.other_teams.values())

    def find_team(self, tid: int) -> Optional[Team]:
        """Look up a team in either league (primary or pipeline partner)."""
        return self.teams.get(tid) or self.other_teams.get(tid)

    def recruit_players(self) -> List[Player]:
        return [self.players[pid] for pid in self.recruits if pid in self.players]

    def add_player(self, player: Player) -> None:
        self.players[player.pid] = player

    def register_team(self, team: Team) -> None:
        self.teams[team.tid] = team

    def register_other_team(self, team: Team) -> None:
        self.other_teams[team.tid] = team

    def free_agent_players(self) -> List[Player]:
        return [self.players[pid] for pid in self.free_agents if pid in self.players]

    # -- draft picks --------------------------------------------------------
    def find_pick(self, year: int, round: int, original_tid: int) -> Optional[DraftPick]:
        for p in self.draft_picks:
            if p.year == year and p.round == round and p.original_tid == original_tid:
                return p
        return None

    def picks_owned_by(self, tid: int) -> List[DraftPick]:
        picks = [p for p in self.draft_picks if p.owner_tid == tid]
        picks.sort(key=lambda p: (p.year, p.round, p.original_tid))
        return picks

    # -- roster transactions ------------------------------------------------
    def sign_player(self, pid: int, tid: int, contract: Contract) -> None:
        player = self.players[pid]
        if player.team_id is not None and player.team_id in self.teams:
            self.teams[player.team_id].remove_player(pid)
        if pid in self.free_agents:
            self.free_agents.remove(pid)
        player.team_id = tid
        player.contract = contract
        self.teams[tid].add_player(pid)

    def release_player(self, pid: int) -> None:
        """Waive a player to free agency (dead money is ignored in Phase 1)."""
        player = self.players[pid]
        if player.team_id is not None and player.team_id in self.teams:
            self.teams[player.team_id].remove_player(pid)
        player.team_id = None
        player.contract = Contract.free_agent()
        if pid not in self.free_agents:
            self.free_agents.append(pid)

    def transfer_player(self, pid: int, to_tid: int) -> None:
        """Move a player between teams keeping their contract (used by trades)."""
        player = self.players[pid]
        if player.team_id is not None and player.team_id in self.teams:
            self.teams[player.team_id].remove_player(pid)
        player.team_id = to_tid
        player.contract.years_with_team = 0   # lost Bird rights on the new team
        self.teams[to_tid].add_player(pid)

    # -- serialization ------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "rng_seed": self.rng.seed,
            "rng_state": self.rng.get_state(),
            "season_year": self.season_year,
            "phase": self.phase,
            "day": self.day,
            "teams": {str(t): team.to_dict() for t, team in self.teams.items()},
            "players": {str(p): pl.to_dict() for p, pl in self.players.items()},
            "schedule": [g.to_dict() for g in self.schedule],
            "free_agents": list(self.free_agents),
            "draft_class": self.draft_class.to_dict() if self.draft_class else None,
            "draft_picks": [p.to_dict() for p in self.draft_picks],
            "trade_offers": list(self.trade_offers),
            "offer_cooldowns": {str(k): v for k, v in self.offer_cooldowns.items()},
            "bracket": self.bracket,
            "user_team_id": self.user_team_id,
            "season_games": self.season_games,
            "salary_cap": self.salary_cap,
            "luxury_tax_line": self.luxury_tax_line,
            "first_apron": self.first_apron,
            "mode": self.mode,
            "college_economy": self.college_economy,
            "other_teams": {str(t): team.to_dict() for t, team in self.other_teams.items()},
            "recruits": list(self.recruits),
            "pipeline": self.pipeline,
            "history": list(self.history),
            "next_pid": self._next_pid,
            "next_gid": self._next_gid,
            "next_offer_id": self._next_offer_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "World":
        rng = Rng.from_state(d.get("rng_seed"), d.get("rng_state"))
        w = cls(rng=rng)
        w.season_year = d["season_year"]
        w.phase = d["phase"]
        w.day = d["day"]
        w.teams = {int(t): Team.from_dict(td) for t, td in d.get("teams", {}).items()}
        w.players = {int(p): Player.from_dict(pd) for p, pd in d.get("players", {}).items()}
        w.schedule = [Game.from_dict(gd) for gd in d.get("schedule", [])]
        w.free_agents = list(d.get("free_agents", []))
        dc = d.get("draft_class")
        w.draft_class = DraftClass.from_dict(dc) if dc else None
        w.draft_picks = [DraftPick.from_dict(pd) for pd in d.get("draft_picks", [])]
        w.trade_offers = list(d.get("trade_offers", []))
        w.offer_cooldowns = {int(k): v for k, v in d.get("offer_cooldowns", {}).items()}
        w.bracket = d.get("bracket")
        w.user_team_id = d.get("user_team_id")
        w.season_games = d.get("season_games", 82)
        w.salary_cap = d.get("salary_cap", SALARY_CAP)
        w.luxury_tax_line = d.get("luxury_tax_line", LUXURY_TAX_LINE)
        w.first_apron = d.get("first_apron", FIRST_APRON)
        w.mode = d.get("mode", "nba")
        w.college_economy = d.get("college_economy", DEFAULT_COLLEGE_ECONOMY)
        w.other_teams = {int(t): Team.from_dict(td) for t, td in d.get("other_teams", {}).items()}
        w.recruits = list(d.get("recruits", []))
        w.pipeline = d.get("pipeline")
        w.history = list(d.get("history", []))
        w._next_pid = d.get("next_pid", max(w.players, default=0) + 1)
        w._next_gid = d.get("next_gid", 1)
        w._next_offer_id = d.get("next_offer_id", 1)
        return w
