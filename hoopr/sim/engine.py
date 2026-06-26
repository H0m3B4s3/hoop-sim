"""Possession-by-possession game simulation.

The engine resolves one offensive trip at a time: turnover check, shooter + shot-type selection,
make/miss with foul and free throws, then rebound (offensive rebounds extend the trip). Players
tire, pick up fouls, and get substituted on a deficit-vs-fatigue rotation. Tactics feed in via
:mod:`hoopr.sim.ratings`. Set ``collect_pbp=True`` to capture a readable play-by-play log.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from hoopr.config import (BASE_SECONDS_PER_POSSESSION, HOME_COURT_BONUS, IN_GAME_INJURY_RATE,
                          OT_SECONDS, QUARTER_SECONDS, QUARTERS)
from hoopr.models.player import Player
from hoopr.models.team import Team
from hoopr.sim import ratings as R
from hoopr.sim.boxscore import GameResult, PBPEvent
from hoopr.sim.ratings import LineupCache, build_lineup_cache

# -- tunables (calibrated so PPP ~1.10 and pace ~99) -------------------------
FATIGUE_GAIN = 0.115
FATIGUE_RECOVER = 0.20
FATIGUE_MAKE_PENALTY = 0.00060
SUB_INTERVAL = 168          # game-seconds between rotation checks
FOUL_OUT = 6
MAX_PUTBACKS = 3


def _stamina_factor(p: Player) -> float:
    return 1.15 - p.ratings["stamina"] / 200.0


def _weighted_index(rng, weights: List[float]) -> int:
    return rng.choices(range(len(weights)), weights=weights, k=1)[0]


class _TeamState:
    def __init__(self, world, team: Team, is_home: bool) -> None:
        self.team = team
        self.abbrev = team.abbrev
        self.is_home = is_home
        self.players: Dict[int, Player] = {pid: world.player(pid) for pid in team.roster}
        self.available: List[int] = [pid for pid in team.roster
                                     if world.player(pid).available]
        self.unavailable: set = set()        # fouled out or injured mid-game
        self.on_court: List[int] = []
        self.secs_played: Dict[int, float] = {pid: 0.0 for pid in self.available}
        self.fatigue: Dict[int, float] = {pid: 0.0 for pid in self.available}
        self.fouls: Dict[int, int] = {pid: 0 for pid in self.available}
        self.target_secs: Dict[int, float] = {
            pid: team.minutes_target.get(pid, 0) * 60.0 for pid in self.available}
        self.cache: Optional[LineupCache] = None

    def players_on_court(self) -> List[Player]:
        return [self.players[pid] for pid in self.on_court]

    def rebuild_cache(self) -> None:
        self.cache = build_lineup_cache(self.players_on_court())

    def choose_lineup(self, game_secs: float) -> None:
        candidates = [pid for pid in self.available if pid not in self.unavailable]
        if len(candidates) <= 5:
            self.on_court = list(candidates)
            self.rebuild_cache()
            return

        def priority(pid: int) -> float:
            remaining = max(0.0, self.target_secs[pid] - self.secs_played[pid])
            foul_pen = 0.0
            f = self.fouls[pid]
            if f >= 5:
                foul_pen = 5000
            elif f >= 4:
                foul_pen = 1800
            elif f >= 3 and game_secs < 1440:
                foul_pen = 600
            starter_bonus = 250.0 if pid in self.team.starters else 0.0
            return remaining - self.fatigue[pid] * 22.0 - foul_pen + starter_bonus

        candidates.sort(key=priority, reverse=True)
        self.on_court = candidates[:5]
        self.rebuild_cache()

    def avg_fatigue(self) -> float:
        if not self.on_court:
            return 0.0
        return sum(self.fatigue[pid] for pid in self.on_court) / len(self.on_court)

    def ball_security(self) -> float:
        oc = self.players_on_court()
        if not oc:
            return 70.0
        return sum(0.6 * p.ratings["ball_handle"] + 0.4 * p.ratings["off_iq"] for p in oc) / len(oc)


class GameSim:
    def __init__(self, world, home: Team, away: Team, *, collect_pbp: bool = False) -> None:
        self.world = world
        self.rng = world.rng
        self.collect_pbp = collect_pbp
        self.home = _TeamState(world, home, is_home=True)
        self.away = _TeamState(world, away, is_home=False)
        self.result = GameResult(home_tid=home.tid, away_tid=away.tid)
        self.quarter = 1
        self.clock = QUARTER_SECONDS
        self.game_secs = 0.0
        self._next_sub = SUB_INTERVAL

    # -- public -------------------------------------------------------------
    def play(self) -> GameResult:
        for state, starters in ((self.home, self.home.team.starters),
                                (self.away, self.away.team.starters)):
            state.on_court = [pid for pid in starters if pid in state.available][:5]
            if len(state.on_court) < 5:
                state.choose_lineup(0.0)
            else:
                state.rebuild_cache()
        self.result.home_starters = list(self.home.on_court)
        self.result.away_starters = list(self.away.on_court)

        offense, defense = (self.home, self.away) if self.rng.chance(0.5) else (self.away, self.home)
        for q in range(1, QUARTERS + 1):
            self.quarter = q
            offense, defense = self._play_period(offense, defense, QUARTER_SECONDS)

        while self.result.home_score == self.result.away_score:
            self.quarter += 1
            self.result.overtimes += 1
            offense, defense = self._play_period(offense, defense, OT_SECONDS)

        self._finalize()
        return self.result

    # -- period loop --------------------------------------------------------
    def _play_period(self, offense: _TeamState, defense: _TeamState, length: int):
        self.clock = length
        period_home = self.result.home_score
        period_away = self.result.away_score
        self.home.choose_lineup(self.game_secs)
        self.away.choose_lineup(self.game_secs)

        while self.clock > 0:
            poss_secs = self._possession_seconds(offense, defense)
            if poss_secs > self.clock:
                poss_secs = self.clock
            self.clock -= poss_secs
            self.game_secs += poss_secs

            if self.game_secs >= self._next_sub:
                self.home.choose_lineup(self.game_secs)
                self.away.choose_lineup(self.game_secs)
                self._next_sub += SUB_INTERVAL

            self._resolve_possession(offense, defense)
            self._apply_fatigue(poss_secs)
            self._injury_check(offense)
            self._injury_check(defense)
            offense, defense = defense, offense

        self.result.line_score.append(
            (self.result.home_score - period_home, self.result.away_score - period_away))
        return offense, defense

    def _possession_seconds(self, offense: _TeamState, defense: _TeamState) -> float:
        pf = (R.PACE_FACTOR[offense.team.tactics.pace]
              + R.PACE_FACTOR[defense.team.tactics.pace]) / 2.0
        mean = BASE_SECONDS_PER_POSSESSION * pf
        if self._is_clutch():
            mean *= 1.12
        return max(3.0, min(24.0, self.rng.gauss(mean, 4.0)))

    def _is_clutch(self) -> bool:
        if self.quarter < QUARTERS:
            return False
        margin = abs(self.result.home_score - self.result.away_score)
        return self.clock <= 300 and margin <= 6

    # -- possession ---------------------------------------------------------
    def _resolve_possession(self, off: _TeamState, deff: _TeamState) -> None:
        if not off.on_court or not deff.on_court:
            return
        oc, dc = off.cache, deff.cache
        scheme = R.DEF_SCHEME[deff.team.tactics.def_scheme]
        pressure = R.DEF_PRESSURE[deff.team.tactics.def_pressure]
        clutch = self._is_clutch()

        if self._maybe_turnover(off, deff, oc, dc, scheme, pressure):
            return

        putbacks = 0
        while True:
            self._take_shot(off, deff, oc, dc, scheme, pressure, clutch, putback=putbacks > 0)
            if not self._last_shot_live:
                break
            oreb_p = self._oreb_prob(off, deff, oc, dc)
            if self.rng.chance(oreb_p) and putbacks < MAX_PUTBACKS:
                self._credit_rebound(off, oc, offensive=True)
                putbacks += 1
                continue
            self._credit_rebound(deff, dc, offensive=False)
            break

    def _maybe_turnover(self, off, deff, oc, dc, scheme, pressure) -> bool:
        to_p = 0.135 - (off.ball_security() - 70) * 0.0011 \
            + (dc.avg_steal - 70) * 0.0011 + pressure[2]
        to_p = max(0.05, min(0.22, to_p))
        if not self.rng.chance(to_p):
            return False
        # who loses it
        loser_idx = _weighted_index(self.rng, oc.usage)
        loser = oc.players[loser_idx]
        self.result.line(loser.pid).tov += 1
        steal_p = max(0.30, min(0.78, 0.52 + (dc.avg_steal - 70) * 0.005 + scheme[2] + pressure[0]))
        if self.rng.chance(steal_p):
            thief_idx = _weighted_index(self.rng, [p.ratings["steal"] for p in dc.players])
            thief = dc.players[thief_idx]
            self.result.line(thief.pid).stl += 1
            self._log(deff.team.tid, f"{thief.short_name} steals it from {loser.short_name}")
        else:
            self._log(off.team.tid, f"{loser.short_name} turns it over")
        return True

    def _take_shot(self, off, deff, oc, dc, scheme, pressure, clutch, putback) -> None:
        shooter_idx = self._pick_shooter(off, oc, putback)
        shooter = oc.players[shooter_idx]
        shot_type = self._pick_shot_type(shooter, off, putback)

        home_edge = HOME_COURT_BONUS if off.is_home else 0.0
        fat_pen = off.avg_fatigue() * FATIGUE_MAKE_PENALTY
        # Catch-up: trailing teams press, leaders ease off. Compresses garbage-time blowouts
        # without changing who is favored (symmetric, small, capped).
        off_margin = ((self.result.home_score - self.result.away_score) if off.is_home
                      else (self.result.away_score - self.result.home_score))
        comeback = max(-0.030, min(0.030, -off_margin * 0.0011))
        edge = home_edge - fat_pen + comeback
        r = shooter.ratings
        if shot_type == "rim":
            make_p = (0.578 + (r["finishing"] - 70) * 0.0030 - (dc.interior_anchor - 70) * 0.0026
                      + edge + scheme[1] + pressure[3])
            foul_p = 0.195 + (r["draw_foul"] - 70) * 0.002 + pressure[1]
        elif shot_type == "mid":
            make_p = (0.380 + (r["mid_range"] - 70) * 0.0030 - (dc.avg_perimeter_def - 70) * 0.0021
                      + edge)
            foul_p = 0.06 + (r["draw_foul"] - 70) * 0.0015 + pressure[1] * 0.5
        else:  # three
            make_p = (0.330 + (r["three_point"] - 70) * 0.0034
                      - (dc.avg_perimeter_def - 70) * 0.0021 + edge + scheme[0])
            foul_p = 0.05 + (r["draw_foul"] - 70) * 0.001
        if clutch:
            make_p += (r["clutch"] - 70) * 0.0008
        make_p = max(0.02, min(0.97, make_p))
        foul_p = max(0.01, min(0.40, foul_p))

        is_three = shot_type == "three"
        value = 3 if is_three else 2
        made = self.rng.chance(make_p)
        fouled = self.rng.chance(foul_p)
        line = self.result.line(shooter.pid)
        self._last_shot_live = False

        if fouled and not made:
            # shooting foul on a miss -> free throws only (no FGA charged)
            self._commit_foul(deff, dc)
            n = 3 if is_three else 2
            made_fts, last_made = self._shoot_fts(shooter, n)
            self._score(off, deff, made_fts)
            if not last_made:
                self._last_shot_live = True
            self._log(off.team.tid, f"{shooter.short_name} draws a foul, {made_fts}/{n} FT")
            return

        # shot is charged as an attempt
        line.fga += 1
        if is_three:
            line.tpa += 1
        if made:
            line.fgm += 1
            line.pts += value
            if is_three:
                line.tpm += 1
            self._score(off, deff, value)
            self._maybe_assist(off, oc, shooter, shot_type)
            desc = {"rim": "drives for the layup", "mid": "hits the jumper",
                    "three": "drains the three"}[shot_type]
            if fouled:  # and-1
                self._commit_foul(deff, dc)
                made_ft, _ = self._shoot_fts(shooter, 1)
                self._score(off, deff, made_ft)
                self._log(off.team.tid, f"{shooter.short_name} {desc} +1 (and-one)")
            else:
                self._log(off.team.tid, f"{shooter.short_name} {desc}")
        else:
            # a real miss -> possible block, then live rebound
            if shot_type in ("rim", "mid"):
                self._maybe_block(deff, dc, shot_type)
            self._last_shot_live = True

    # -- shot helpers -------------------------------------------------------
    def _pick_shooter(self, off, oc, putback) -> int:
        conc = R.BALL_MOVEMENT_CONCENTRATION[off.team.tactics.ball_movement]
        if putback:
            weights = [w * (1.4 if p.position in ("PF", "C") else 1.0)
                       for w, p in zip(oc.rebound_w, oc.players)]
        else:
            weights = [u ** conc for u in oc.usage]
        return _weighted_index(self.rng, weights)

    def _pick_shot_type(self, shooter: Player, off, putback) -> str:
        if putback:
            return "rim"
        r = shooter.ratings
        focus_rim, focus_three = R.OFF_FOCUS_SHOT[off.team.tactics.off_focus]
        rim = max(0.03, 0.36 + (r["finishing"] - 70) * 0.004 + (r["athleticism"] - 70) * 0.002
                  + focus_rim)
        three = max(0.03, 0.32 + (r["three_point"] - 70) * 0.006 + focus_three)
        mid = max(0.04, 1.0 - rim - three)
        total = rim + three + mid
        roll = self.rng.random() * total
        if roll < rim:
            return "rim"
        if roll < rim + three:
            return "three"
        return "mid"

    def _shoot_fts(self, shooter: Player, n: int):
        ft_pct = max(0.40, min(0.97, 0.05 + shooter.ratings["free_throw"] * 0.0095))
        line = self.result.line(shooter.pid)
        makes = 0
        last_made = False
        for _ in range(n):
            line.fta += 1
            if self.rng.chance(ft_pct):
                line.ftm += 1
                line.pts += 1
                makes += 1
                last_made = True
            else:
                last_made = False
        return makes, last_made

    def _maybe_assist(self, off, oc, shooter: Player, shot_type: str) -> None:
        base = {"three": 0.82, "mid": 0.45, "rim": 0.50}[shot_type]
        base += R.BALL_MOVEMENT_ASSIST[off.team.tactics.ball_movement]
        base = max(0.05, min(0.95, base))
        if not self.rng.chance(base):
            return
        others = [(i, p) for i, p in enumerate(oc.players) if p.pid != shooter.pid]
        if not others:
            return
        weights = [oc.passing_w[i] for i, _ in others]
        idx = _weighted_index(self.rng, weights)
        passer = others[idx][1]
        self.result.line(passer.pid).ast += 1

    def _maybe_block(self, deff, dc, shot_type: str) -> None:
        block_p = max(0.0, (dc.block_anchor - 62) * 0.004)
        if shot_type == "mid":
            block_p *= 0.4
        block_p = min(0.16, block_p)
        if self.rng.chance(block_p):
            idx = _weighted_index(self.rng, [p.ratings["block"] for p in dc.players])
            blocker = dc.players[idx]
            self.result.line(blocker.pid).blk += 1
            self._log(deff.team.tid, f"{blocker.short_name} blocks the shot")

    def _commit_foul(self, deff, dc) -> Player:
        idx = _weighted_index(self.rng, dc.foul_w)
        fouler = dc.players[idx]
        self.result.line(fouler.pid).pf += 1
        deff.fouls[fouler.pid] = deff.fouls.get(fouler.pid, 0) + 1
        if deff.fouls[fouler.pid] >= FOUL_OUT:
            deff.unavailable.add(fouler.pid)
            if fouler.pid in deff.on_court:
                deff.choose_lineup(self.game_secs)
            self._log(deff.team.tid, f"{fouler.short_name} fouls out")
        return fouler

    def _oreb_prob(self, off, deff, oc, dc) -> float:
        base = 0.24 + (oc.oreb_power - dc.dreb_power) * 0.003
        base += R.REBOUND_FOCUS_OREB[off.team.tactics.rebound_focus]
        return max(0.08, min(0.45, base))

    def _credit_rebound(self, team, cache, offensive: bool) -> None:
        if not cache.players:
            return
        idx = _weighted_index(self.rng, cache.rebound_w)
        rebounder = cache.players[idx]
        if offensive:
            self.result.line(rebounder.pid).oreb += 1
        else:
            self.result.line(rebounder.pid).dreb += 1

    # -- bookkeeping --------------------------------------------------------
    def _score(self, off, deff, points: int) -> None:
        """Apply points to the team score and on-court plus/minus."""
        if points <= 0:
            return
        if off.is_home:
            self.result.home_score += points
        else:
            self.result.away_score += points
        for pid in off.on_court:
            self.result.line(pid).plus_minus += points
        for pid in deff.on_court:
            self.result.line(pid).plus_minus -= points

    def _apply_fatigue(self, poss_secs: float) -> None:
        for state in (self.home, self.away):
            on = set(state.on_court)
            for pid in state.available:
                if pid in on:
                    state.secs_played[pid] += poss_secs
                    state.fatigue[pid] = min(
                        100.0, state.fatigue[pid]
                        + poss_secs * FATIGUE_GAIN * _stamina_factor(state.players[pid]))
                elif pid not in state.unavailable:
                    state.fatigue[pid] = max(0.0, state.fatigue[pid] - poss_secs * FATIGUE_RECOVER)

    def _injury_check(self, state: _TeamState) -> None:
        for pid in list(state.on_court):
            p = state.players[pid]
            rate = IN_GAME_INJURY_RATE * (1.0 + (70 - p.ratings["durability"]) * 0.01)
            if self.rng.chance(max(0.0, rate)):
                games, severity = self._injury_severity()
                self.result.injuries.append((pid, games, "in-game injury", severity))
                state.unavailable.add(pid)
                state.choose_lineup(self.game_secs)
                self._log(state.team.tid, f"{p.short_name} is injured and leaves the game")

    def _injury_severity(self):
        roll = self.rng.random()
        if roll < 0.6:
            return self.rng.randint(1, 3), "minor"
        if roll < 0.9:
            return self.rng.randint(4, 12), "moderate"
        return self.rng.randint(15, 45), "major"

    def _log(self, tid: int, text: str) -> None:
        if not self.collect_pbp:
            return
        self.result.pbp.append(PBPEvent(
            quarter=self.quarter, seconds_left=int(self.clock),
            home_score=self.result.home_score, away_score=self.result.away_score,
            tid=tid, text=text))

    def _finalize(self) -> None:
        # record seconds played into each player's box line
        for state in (self.home, self.away):
            for pid, secs in state.secs_played.items():
                if secs > 0 or pid in self.result.box:
                    line = self.result.line(pid)
                    line.secs = int(round(secs))
                    line.gp = 1
                    if pid in (self.result.home_starters + self.result.away_starters):
                        line.gs = 1


def simulate_game(world, home: Team, away: Team, *, collect_pbp: bool = False) -> GameResult:
    """Convenience wrapper: simulate one game and return its result."""
    return GameSim(world, home, away, collect_pbp=collect_pbp).play()
