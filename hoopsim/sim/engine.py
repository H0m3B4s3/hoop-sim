"""Possession-by-possession game simulation.

The engine resolves one offensive trip at a time: turnover check, shooter + shot-type selection,
make/miss with foul and free throws, then rebound (offensive rebounds extend the trip). Players
tire, pick up fouls, and get substituted on a deficit-vs-fatigue rotation. Tactics feed in via
:mod:`hoopr.sim.ratings`. Set ``collect_pbp=True`` to capture a readable play-by-play log.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from hoopsim.config import HOME_COURT_BONUS, IN_GAME_INJURY_RATE, OT_SECONDS, game_format
from hoopsim.models.attributes import POSITIONS
from hoopsim.models.coach import profile_for
from hoopsim.models.player import Player
from hoopsim.models.team import Team, position_distance
from hoopsim.sim import ratings as R
from hoopsim.sim.boxscore import GameResult, PBPEvent
from hoopsim.sim.coach import Coach, CoachOrders, CoachView, PlayerView, PRESET_WEIGHTS
from hoopsim.sim.ratings import LineupCache, build_lineup_cache

# -- tunables (calibrated so PPP ~1.10 and pace ~99) -------------------------
FATIGUE_GAIN = 0.115
FATIGUE_RECOVER = 0.20
FATIGUE_MAKE_PENALTY = 0.00060
SUB_INTERVAL = 168          # game-seconds between rotation checks
# Soft positional balance: a player costs this much priority per "position of distance" from the
# slot being filled, so the engine fields a sensible five (no all-guard lineups) without rigid
# per-position subs. Tuned per branch since the two priority functions live on different scales.
POS_BALANCE_WEIGHT = 200.0          # normal rotation (priority is in remaining-seconds units)
CLUTCH_POS_BALANCE_WEIGHT = 25.0    # crunch time (priority is overall*10; keep talent dominant)
FOUL_OUT = 6
MAX_PUTBACKS = 3
BONUS_FOULS = 5             # team fouls in a period that put the opponent in the bonus

# -- interactive end-game coaching window -----------------------------------
COACH_WINDOW_SECONDS = 120.0   # final-period clock at/under which the coach is consulted
COACH_MARGIN = 12              # only when the game is within this many points
# A free-throw set opens a legal sub window before the final attempt. We only surface it (so the
# user can reset their rebounding/defense for the live ball) in genuinely tense spots, to avoid
# prompting on every whistle.
FT_SUB_WINDOW_SECONDS = 60.0   # final-period clock at/under which an FT sub window is offered
FT_SUB_MARGIN = 5              # only within this many points (a one-possession game)
TIMEOUT_FATIGUE_RELIEF = 0.55  # on-court fatigue multiplier after a timeout
DRAW_PLAY_BONUS = 0.05         # make-probability edge on the possession after a timeout


class _SubBreak:
    """Marker a resolution generator yields at a free-throw dead ball, before the final attempt.
    Carries the offense/defense states so the driver can offer the user a substitution."""
    __slots__ = ("off", "deff")

    def __init__(self, off: "_TeamState", deff: "_TeamState") -> None:
        self.off = off
        self.deff = deff


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
        self.timeouts: int = game_format(team.league)["timeouts"]
        self.period_fouls: int = 0                      # team fouls in the current period
        self.locked_lineup: Optional[List[int]] = None  # coach-pinned on-court five

    def players_on_court(self) -> List[Player]:
        return [self.players[pid] for pid in self.on_court]

    def rebuild_cache(self) -> None:
        self.cache = build_lineup_cache(self.players_on_court())

    def choose_lineup(self, game_secs: float, clutch: bool = False) -> None:
        candidates = [pid for pid in self.available if pid not in self.unavailable]
        if len(candidates) <= 5:
            self.on_court = list(candidates)
            self.rebuild_cache()
            return

        if self.locked_lineup is not None:
            locked = [pid for pid in self.locked_lineup if pid in candidates]
            if len(locked) == 5:
                self.on_court = locked
                self.rebuild_cache()
                return
            self.locked_lineup = None    # foul-out/injury broke the pinned five; auto-fill again

        if clutch:
            # Crunch time: ride your best closers regardless of how many minutes they've banked
            # (best overall on the floor, lightly adjusted for exhaustion and foul trouble).
            pos_weight = CLUTCH_POS_BALANCE_WEIGHT

            def priority(pid: int) -> float:
                foul_pen = 4000.0 if self.fouls[pid] >= 5 else 0.0
                return self.players[pid].overall * 10.0 - self.fatigue[pid] * 0.4 - foul_pen
        else:
            fatigue_weight = profile_for(self.team).fatigue_weight   # head-coach sub tendency
            pos_weight = POS_BALANCE_WEIGHT

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
                return remaining - self.fatigue[pid] * fatigue_weight - foul_pen + starter_bonus

        # Position-aware greedy fill: each slot PG..C takes the best remaining candidate after a
        # soft penalty for playing out of position, so the five stays positionally sensible.
        scores = {pid: priority(pid) for pid in candidates}
        remaining = list(candidates)
        chosen: List[int] = []
        for slot in POSITIONS:
            best = max(remaining,
                       key=lambda pid: scores[pid] - pos_weight * position_distance(self.players[pid], slot))
            chosen.append(best)
            remaining.remove(best)
        self.on_court = chosen
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
    def __init__(self, world, home: Team, away: Team, *, collect_pbp: bool = False,
                 coach: Optional[Coach] = None, coach_tid: Optional[int] = None) -> None:
        self.world = world
        self.rng = world.rng
        self.collect_pbp = collect_pbp or coach is not None
        self.coach = coach
        self.coach_tid = coach_tid if coach is not None else None
        self.home = _TeamState(world, home, is_home=True)
        self.away = _TeamState(world, away, is_home=False)
        fmt = game_format(home.league)
        self.periods = fmt["periods"]
        self.period_seconds = fmt["period_seconds"]
        self.base_poss_seconds = fmt["base_poss_seconds"]
        self.shot_clock = fmt["shot_clock"]
        self.result = GameResult(home_tid=home.tid, away_tid=away.tid,
                                 period_label=fmt["label"])
        self.quarter = 1
        self.clock = self.period_seconds
        self.game_secs = 0.0
        self._next_sub = SUB_INTERVAL
        self._prev_crunch = False
        self._draw_play_tid: Optional[int] = None   # team that just took a timeout (one-poss boost)
        self._play_boost = 0.0
        self._three_bias = 0.0                       # chance this trip is forced into a three
        self._iso_set = False                         # funnel this trip's usage to the top scorer
        self._rim_set = 0.0                           # extra rim-shot bias this trip (pound inside)
        self._first_engagement = True

    # -- public -------------------------------------------------------------
    def play(self) -> GameResult:
        """Play the whole game, driving any blocking ``coach`` synchronously."""
        driver = self.coach_session()
        try:
            view = next(driver)
            while True:
                orders = self.coach.decide(view) if self.coach is not None else None
                view = driver.send(orders)
        except StopIteration:
            pass
        return self.result

    def coach_session(self):
        """A generator driving the game that suspends at each user crunch-time decision.

        Pump it with ``next()`` and ``gen.send(orders)``: every yielded value is a
        :class:`~hoopr.sim.coach.CoachView` to act on, resumed with the user's
        :class:`~hoopr.sim.coach.CoachOrders`. When it raises ``StopIteration`` the finished
        :class:`~hoopr.sim.boxscore.GameResult` is on ``self.result``. With no coach (or in a
        blowout that never reaches the window) it simply never yields. Possession narration is
        delivered through ``coach.narrate`` as each trip resolves.
        """
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
        for q in range(1, self.periods + 1):
            self.quarter = q
            offense, defense = yield from self._play_period(offense, defense, self.period_seconds)

        while self.result.home_score == self.result.away_score:
            self.quarter += 1
            self.result.overtimes += 1
            offense, defense = yield from self._play_period(offense, defense, OT_SECONDS)

        self._finalize()

    # -- period loop --------------------------------------------------------
    def _set_lineups(self) -> None:
        """Re-pick both lineups, each side honoring its own crunch-time instruction."""
        self.home.choose_lineup(self.game_secs, clutch=self._clutch_for(self.home))
        self.away.choose_lineup(self.game_secs, clutch=self._clutch_for(self.away))

    def _clutch_for(self, state: _TeamState) -> bool:
        """A team rides its closers in the clutch unless it's told to keep the rotation."""
        return self._is_crunch() and state.team.tactics.crunch_lineup != "Rotation"

    def _play_period(self, offense: _TeamState, defense: _TeamState, length: int):
        """Possession loop for one period. A generator: it yields a CoachView at each user
        crunch decision and resumes with the CoachOrders sent back in."""
        self.clock = length
        period_home = self.result.home_score
        period_away = self.result.away_score
        self.home.period_fouls = 0
        self.away.period_fouls = 0
        self._set_lineups()

        while self.clock > 0:
            crunch = self._is_crunch()
            if self.game_secs >= self._next_sub or crunch != self._prev_crunch:
                self._set_lineups()
                self._next_sub = self.game_secs + SUB_INTERVAL
                self._prev_crunch = crunch

            orders = None
            if self.coach is not None and self._coach_engaged(offense, defense):
                user = offense if offense.team.tid == self.coach_tid else defense
                orders = yield self._build_view(offense, defense, user)
                if orders is None:
                    orders = CoachOrders()
                self._apply_orders(orders, offense, defense)
                self._ai_timeout(offense, defense)

            intentional, foul_up_3, poss_secs = self._plan_possession(offense, defense, orders)
            if poss_secs > self.clock:
                poss_secs = self.clock
            self.clock -= poss_secs
            self.game_secs += poss_secs

            pbp_mark = len(self.result.pbp)
            if intentional:
                gen = self._intentional_foul_g(offense, defense)
            elif foul_up_3:
                gen = self._foul_up_3_g(offense, defense)
            else:
                gen = self._resolve_possession_g(offense, defense)
            yield from self._drive_resolution(gen)
            if orders is not None:
                self.coach.narrate(self.result.pbp[pbp_mark:])
            self._apply_fatigue(poss_secs)
            self._injury_check(offense)
            self._injury_check(defense)
            offense, defense = defense, offense

        self.result.line_score.append(
            (self.result.home_score - period_home, self.result.away_score - period_away))
        return offense, defense

    def _drive_resolution(self, gen):
        """Run a possession-resolution generator, surfacing its free-throw sub windows.

        The cores (``_resolve_possession_g`` and the deliberate-foul variants) pause with a
        :class:`_SubBreak` before the final free throw of a set. When the situation is tense
        enough (:meth:`_ft_sub_window`) we hand the user a substitution-only decision so a fresh
        five contests the live rebound and the next trip; otherwise we resume untouched. Non-coached
        sims drain the cores through synchronous wrappers and never see these breaks.
        """
        try:
            brk = next(gen)
            while True:
                if self.coach is not None and self._ft_sub_window():
                    user = brk.off if brk.off.team.tid == self.coach_tid else brk.deff
                    orders = yield self._build_view(brk.off, brk.deff, user, sub_only=True)
                    if orders is not None:
                        self._apply_orders(orders, brk.off, brk.deff)
                brk = gen.send(None)
        except StopIteration:
            return

    def _ft_sub_window(self) -> bool:
        """True when a free-throw sub window is worth offering: final period, one-possession game,
        late, and the user has a bench player to bring in."""
        if self.coach_tid is None or self.quarter < self.periods:
            return False
        margin = abs(self.result.home_score - self.result.away_score)
        if self.clock > FT_SUB_WINDOW_SECONDS or margin > FT_SUB_MARGIN:
            return False
        user = self.home if self.home.team.tid == self.coach_tid else self.away
        return any(pid not in user.on_court and pid not in user.unavailable
                   for pid in user.available)

    # -- interactive coaching ----------------------------------------------
    def _coach_engaged(self, offense: _TeamState, defense: _TeamState) -> bool:
        """True when the human coach should be consulted before this possession."""
        if self.coach_tid is None or self.quarter < self.periods:
            return False
        if offense.team.tid != self.coach_tid and defense.team.tid != self.coach_tid:
            return False
        margin = abs(self.result.home_score - self.result.away_score)
        return self.clock <= COACH_WINDOW_SECONDS and margin <= COACH_MARGIN

    def _plan_possession(self, offense, defense, orders):
        """Decide whether this trip is a deliberate foul and how long it should run."""
        user_off = offense.team.tid == self.coach_tid
        user_def = defense.team.tid == self.coach_tid
        foul_order = orders.defensive_foul if (orders is not None and user_def) else "auto"

        if foul_order == "foul":
            intentional = True
        elif foul_order == "no":
            intentional = False
        else:
            intentional = self._should_intentional_foul(offense, defense)
        foul_up_3 = (not intentional) and foul_order != "no" \
            and self._should_foul_up_3(offense, defense)

        self._three_bias = 0.0
        self._iso_set = False
        self._rim_set = 0.0
        if intentional or foul_up_3:
            return intentional, foul_up_3, self.rng.uniform(2.5, 5.0)

        # Offensive set: the look to hunt this trip (independent of tempo). quick3 already implies a
        # spread-for-three, so it carries its own bias below.
        off_set = orders.offensive_set if (orders is not None and user_off) else "motion"
        if off_set == "iso":
            self._iso_set = True
        elif off_set == "inside":
            self._rim_set = 0.16
        elif off_set == "spread":
            self._three_bias = 0.45

        tempo = orders.tempo if (orders is not None and user_off) else "normal"
        if tempo == "hold":
            poss_secs = self._hold_seconds()
        elif tempo == "bleed":
            poss_secs = self._bleed_seconds()
        elif tempo == "quick3":
            # Trailing and need points fast: get a quick shot up, and make it a three.
            self._three_bias = 0.70
            poss_secs = self.rng.uniform(3.0, 6.0)
        else:
            poss_secs = self._possession_seconds(offense, defense)
        return False, False, poss_secs

    def _hold_seconds(self) -> float:
        """Hold for the last shot: drain to the buzzer, but never past the shot clock."""
        target = self.clock - self.rng.uniform(1.0, 3.0)
        return max(4.0, min(self.shot_clock - 1.0, target))

    def _bleed_seconds(self) -> float:
        """Leading: chew the shot clock down before still taking a decent look."""
        return max(4.0, min(self.clock, self.shot_clock - self.rng.uniform(1.0, 4.0)))

    def _consult_coach(self, offense: _TeamState, defense: _TeamState):
        """Blocking-coach convenience: ask the coach and apply the orders. Used by the
        synchronous :meth:`play` driver path and by tests; the generator inlines these steps
        around a ``yield`` so the web layer can supply the orders out-of-band."""
        user = offense if offense.team.tid == self.coach_tid else defense
        orders = self.coach.decide(self._build_view(offense, defense, user))
        self._apply_orders(orders, offense, defense)
        return orders

    def _apply_orders(self, orders: CoachOrders, offense: _TeamState, defense: _TeamState) -> None:
        """Apply a possession's coaching orders (substitution + timeout) to the user team."""
        user = offense if offense.team.tid == self.coach_tid else defense
        if orders.lineup:
            valid = [pid for pid in orders.lineup
                     if pid in user.available and pid not in user.unavailable]
            if len(valid) == 5:
                user.locked_lineup = list(valid)
                user.choose_lineup(self.game_secs, clutch=self._clutch_for(user))

        if orders.timeout and user.timeouts > 0:
            user.timeouts -= 1
            for pid in user.on_court:
                user.fatigue[pid] *= TIMEOUT_FATIGUE_RELIEF
            self._draw_play_tid = user.team.tid
            self._log(user.team.tid,
                      f"{user.team.abbrev} call timeout ({user.timeouts} left)")
        self._first_engagement = False

    def _ai_timeout(self, offense: _TeamState, defense: _TeamState) -> None:
        """The AI opponent burns a timeout to settle things when trailing late on offense."""
        opp = offense if offense.team.tid != self.coach_tid else None
        if opp is None or opp.timeouts <= 0:
            return
        off_score, def_score = self._scores(offense)
        if -9 <= (off_score - def_score) < 0 and self.clock <= 45.0 and self.rng.chance(0.15):
            opp.timeouts -= 1
            for pid in opp.on_court:
                opp.fatigue[pid] *= TIMEOUT_FATIGUE_RELIEF
            self._draw_play_tid = opp.team.tid
            self._log(opp.team.tid, f"{opp.team.abbrev} call timeout ({opp.timeouts} left)")

    def _build_view(self, offense: _TeamState, defense: _TeamState,
                    user: _TeamState, *, sub_only: bool = False) -> CoachView:
        opp = defense if user is offense else offense

        def pv(state: _TeamState, pid: int) -> PlayerView:
            p = state.players[pid]
            return PlayerView(pid=pid, name=p.short_name, pos=p.position, overall=p.overall,
                              fouls=state.fouls.get(pid, 0), fatigue=state.fatigue.get(pid, 0.0),
                              secs=state.secs_played.get(pid, 0.0),
                              fouled_out=pid in state.unavailable)

        on_court = [pv(user, pid) for pid in user.on_court]
        bench = [pv(user, pid) for pid in user.available
                 if pid not in user.on_court and pid not in user.unavailable]
        return CoachView(
            quarter=self.quarter, periods=self.periods, clock=self.clock,
            period_label=self.result.period_label,
            home_abbrev=self.home.abbrev, away_abbrev=self.away.abbrev,
            home_score=self.result.home_score, away_score=self.result.away_score,
            user_is_home=user.is_home, user_on_offense=user is offense,
            user_timeouts=user.timeouts, opp_timeouts=opp.timeouts,
            user_in_bonus=opp.period_fouls >= BONUS_FOULS,
            opp_in_bonus=user.period_fouls >= BONUS_FOULS,
            on_court=on_court, bench=bench, first_engagement=self._first_engagement,
            sub_only=sub_only, presets=self._compute_presets(user),
            hint=(self._ft_sub_hint(user, opp) if sub_only
                  else self._coach_hint(user, opp, on_offense=user is offense)))

    def _ft_sub_hint(self, user: _TeamState, opp: _TeamState) -> str:
        user_score = self.result.home_score if user.is_home else self.result.away_score
        opp_score = self.result.away_score if user.is_home else self.result.home_score
        lead = user_score - opp_score
        where = "up" if lead > 0 else "down" if lead < 0 else "tied"
        tail = f" — {where} {abs(lead)}" if lead else " — tied"
        return (f"Free throw coming{tail}. Set your five before the live ball: "
                f"rebounders to corral a miss, your closers to push the other way.")

    def _compute_presets(self, user: _TeamState) -> Dict[str, List[int]]:
        """The best five available players for each situational preset (see PRESET_WEIGHTS).

        Each preset scores every available player by a weighted blend of ratings (``overall`` is the
        composite) and takes the top five. These are *suggestions* the UI loads on one tap; the user
        still confirms, so a positionally odd five is the user's call, not the engine's.
        """
        avail = [pid for pid in user.available if pid not in user.unavailable]
        out: Dict[str, List[int]] = {}
        for key, weights in PRESET_WEIGHTS.items():
            def score(pid: int) -> float:
                p = user.players[pid]
                return sum((p.overall if field == "overall" else p.ratings[field]) * w
                           for field, w in weights.items())
            out[key] = sorted(avail, key=score, reverse=True)[:5]
        return out

    def _coach_hint(self, user: _TeamState, opp: _TeamState, *, on_offense: bool) -> str:
        """A short, situational read for the bench panel — guidance, never a command."""
        user_score = self.result.home_score if user.is_home else self.result.away_score
        opp_score = self.result.away_score if user.is_home else self.result.home_score
        lead = user_score - opp_score
        secs = int(self.clock)
        late = secs <= 24
        if on_offense:
            if lead > 0:
                if late and opp.timeouts == 0:
                    return f"Up {lead} and they have no timeouts — milk the clock and make them foul."
                return f"Up {lead} with the ball — bleed the clock, take a good shot late."
            if lead < 0:
                need3 = lead <= -3
                tail = "you need a three" if need3 else "go get a quick bucket, then get a stop"
                return f"Down {-lead}, {secs}s left — {tail}."
            return f"Tied, {secs}s to go — run something clean, don't settle."
        # defense
        if lead == 3 and secs <= 8:
            return "Up 3 in the final seconds — foul before they can shoot the tying three."
        if lead > 0:
            extra = " They have no timeouts, so a stop likely ends it." if opp.timeouts == 0 else ""
            return f"Up {lead} on defense — get a stop, don't foul a jump shooter.{extra}"
        if lead < 0:
            if late:
                return f"Down {-lead}, {secs}s left — foul now to stop the clock and get the ball back."
            return f"Down {-lead} — get a stop, you can foul if the shot clock favors it."
        return f"Tied, {secs}s on defense — one stop wins it, contest without fouling."

    def _is_crunch(self) -> bool:
        """Final period / OT, close game, under three minutes — ride your best lineup."""
        if self.quarter < self.periods:
            return False
        return self.clock <= 180 and abs(self.result.home_score - self.result.away_score) <= 8

    def _scores(self, offense: _TeamState):
        """(offense_score, defense_score) for the team currently with the ball."""
        off_score = self.result.home_score if offense.is_home else self.result.away_score
        def_score = self.result.away_score if offense.is_home else self.result.home_score
        return off_score, def_score

    def _should_intentional_foul(self, offense: _TeamState, defense: _TeamState) -> bool:
        """The defense (trailing late) fouls to stop the clock and get the ball back.

        Honors the defense's coach instruction: ``Never`` never fouls, ``Aggressive`` starts
        earlier and from a larger deficit, ``Auto`` is the default judgement.
        """
        mode = defense.team.tactics.crunch_foul
        if mode == "Never" or self.quarter < self.periods:
            return False
        off_score, def_score = self._scores(offense)
        lead = off_score - def_score          # offense has the ball; defense trails if lead > 0
        if mode == "Aggressive":
            return 3.0 < self.clock <= 50.0 and 1 <= lead <= 12 and self.rng.chance(0.95)
        return 3.0 < self.clock <= 35.0 and 1 <= lead <= 9 and self.rng.chance(0.85)

    def _should_foul_up_3(self, offense: _TeamState, defense: _TeamState) -> bool:
        """Up exactly 3 in the final seconds, the defense fouls to deny a tying three."""
        if defense.team.tactics.foul_up_3 != "Yes" or self.quarter < self.periods:
            return False
        off_score, def_score = self._scores(offense)
        return 0 < self.clock <= 8.0 and (def_score - off_score) == 3

    def _foul_up_3(self, offense: _TeamState, defense: _TeamState) -> None:
        """Synchronous foul-up-3 (no sub window) for tests and non-coached sims."""
        for _ in self._foul_up_3_g(offense, defense):
            pass

    def _foul_up_3_g(self, offense: _TeamState, defense: _TeamState):
        """Resolve the deliberate foul-up-3 as a defense-IQ vs offense-IQ contest.

        A clean foul puts the offense on the line for two (they can't tie); botching it lets
        the offense get a look up — occasionally even drawing a three-shot foul. A generator: it
        pauses at the free-throw sub window (see :meth:`_drive_resolution`).
        """
        oc, dc = offense.cache, defense.cache
        if not oc.players or not dc.players:
            return
        d_iq = sum(p.ratings["def_iq"] for p in dc.players) / len(dc.players)
        o_iq = sum(p.ratings["off_iq"] for p in oc.players) / len(oc.players)
        clean_p = max(0.45, min(0.92, 0.70 + (d_iq - o_iq) * 0.006))
        shooter = oc.players[_weighted_index(self.rng, oc.usage)]
        if self.rng.chance(clean_p):
            self._commit_foul(defense, dc)
            made, last_made = yield from self._shoot_fts_g(shooter, 2, offense, defense)
            self._score(offense, defense, made)
            self._log(defense.team.tid,
                      f"fouls {shooter.short_name} before the three — {made}/2 FT")
            if not last_made:
                oc, dc = offense.cache, defense.cache     # a sub may have changed the five
                if self.rng.chance(self._oreb_prob(offense, defense, oc, dc)):
                    self._credit_rebound(offense, oc, offensive=True)
                else:
                    self._credit_rebound(defense, dc, offensive=False)
        else:
            self._log(defense.team.tid, f"can't foul in time — {shooter.short_name} gets a look")
            yield from self._resolve_possession_g(offense, defense)

    def _intentional_foul(self, offense: _TeamState, defense: _TeamState) -> None:
        """Synchronous intentional foul (no sub window) for tests and non-coached sims."""
        for _ in self._intentional_foul_g(offense, defense):
            pass

    def _intentional_foul_g(self, offense: _TeamState, defense: _TeamState):
        oc, dc = offense.cache, defense.cache
        if not oc.players or not dc.players:
            return
        self._commit_foul(defense, dc)
        shooter = oc.players[_weighted_index(self.rng, oc.usage)]
        made, last_made = yield from self._shoot_fts_g(shooter, 2, offense, defense)
        self._score(offense, defense, made)
        self._log(offense.team.tid,
                  f"{shooter.short_name} sent to the line on a foul, {made}/2 FT")
        if not last_made:                      # missed the last FT -> live rebound
            oc, dc = offense.cache, defense.cache     # a sub may have changed the five
            if self.rng.chance(self._oreb_prob(offense, defense, oc, dc)):
                self._credit_rebound(offense, oc, offensive=True)
            else:
                self._credit_rebound(defense, dc, offensive=False)

    def _possession_seconds(self, offense: _TeamState, defense: _TeamState) -> float:
        pf = (R.PACE_FACTOR[offense.team.tactics.pace]
              + R.PACE_FACTOR[defense.team.tactics.pace]) / 2.0
        mean = self.base_poss_seconds * pf
        if self._is_clutch():
            mean *= 1.12
        upper = self.base_poss_seconds + 12.0          # ~26.5s NBA, ~30s college
        return max(3.0, min(upper, self.rng.gauss(mean, 4.0)))

    def _is_clutch(self) -> bool:
        if self.quarter < self.periods:
            return False
        margin = abs(self.result.home_score - self.result.away_score)
        return self.clock <= 300 and margin <= 6

    # -- possession ---------------------------------------------------------
    def _resolve_possession(self, off: _TeamState, deff: _TeamState) -> None:
        """Synchronous possession (no sub window) for tests and non-coached sims."""
        for _ in self._resolve_possession_g(off, deff):
            pass

    def _resolve_possession_g(self, off: _TeamState, deff: _TeamState):
        """One possession. A generator: it pauses at any free-throw sub window (a drawn shooting
        foul) so the driver can offer a substitution before the live rebound."""
        if not off.on_court or not deff.on_court:
            return
        # A timeout buys the team that called it one drawn-up possession with a small edge.
        if self._draw_play_tid is not None and off.team.tid == self._draw_play_tid:
            self._play_boost = DRAW_PLAY_BONUS
            self._draw_play_tid = None
        else:
            self._play_boost = 0.0
        oc, dc = off.cache, deff.cache
        scheme = R.DEF_SCHEME[deff.team.tactics.def_scheme]
        pressure = R.DEF_PRESSURE[deff.team.tactics.def_pressure]
        clutch = self._is_clutch()

        if self._maybe_turnover(off, deff, oc, dc, scheme, pressure):
            return

        putbacks = 0
        while True:
            yield from self._take_shot_g(off, deff, oc, dc, scheme, pressure, clutch,
                                         putback=putbacks > 0)
            if not self._last_shot_live:
                break
            oc, dc = off.cache, deff.cache            # a sub at the line may have changed the five
            oreb_p = self._oreb_prob(off, deff, oc, dc)
            if self.rng.chance(oreb_p) and putbacks < MAX_PUTBACKS:
                self._credit_rebound(off, oc, offensive=True)
                putbacks += 1
                continue
            self._credit_rebound(deff, dc, offensive=False)
            break

    def _maybe_turnover(self, off, deff, oc, dc, scheme, pressure) -> bool:
        to_p = 0.135 - (off.ball_security() - 70) * 0.0011 \
            + (dc.avg_steal - 70) * 0.0011 + pressure[2] - self._play_boost * 0.5
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

    def _take_shot_g(self, off, deff, oc, dc, scheme, pressure, clutch, putback):
        """One shot attempt. A generator: a drawn shooting foul pauses at the free-throw sub
        window (via :meth:`_shoot_fts_g`) before the final attempt."""
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
        edge = home_edge - fat_pen + comeback + self._play_boost
        r = shooter.ratings
        # Defender coefficients are held at parity with the matching shooter coefficient so a
        # league-wide ratings drift nets to zero on make probability (scores track skill *gaps*,
        # not absolute level). Parity also keeps an elite shooter from running away from an average
        # defense, which is what produced 160-point regulation games.
        if shot_type == "rim":
            make_p = (0.560 + (r["finishing"] - 70) * 0.0030 - (dc.interior_anchor - 70) * 0.0030
                      + edge + scheme[1] + pressure[3])
            foul_p = 0.195 + (r["draw_foul"] - 70) * 0.002 + pressure[1]
        elif shot_type == "mid":
            make_p = (0.380 + (r["mid_range"] - 70) * 0.0030 - (dc.avg_perimeter_def - 70) * 0.0030
                      + edge)
            foul_p = 0.06 + (r["draw_foul"] - 70) * 0.0015 + pressure[1] * 0.5
        else:  # three
            make_p = (0.330 + (r["three_point"] - 70) * 0.0034
                      - (dc.avg_perimeter_def - 70) * 0.0034 + edge + scheme[0])
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
            made_fts, last_made = yield from self._shoot_fts_g(shooter, n, off, deff)
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
            assister = self._maybe_assist(off, oc, shooter, shot_type)
            assist_note = f" (assist: {assister.short_name})" if assister else ""
            desc = {"rim": "drives for the layup", "mid": "hits the jumper",
                    "three": "drains the three"}[shot_type]
            if fouled:  # and-1
                self._commit_foul(deff, dc)
                made_ft, _ = self._shoot_fts(shooter, 1)
                self._score(off, deff, made_ft)
                self._log(off.team.tid, f"{shooter.short_name} {desc} +1 (and-one){assist_note}")
            else:
                self._log(off.team.tid, f"{shooter.short_name} {desc}{assist_note}")
        else:
            # a real miss -> possible block, then live rebound
            blocked = False
            if shot_type in ("rim", "mid"):
                blocked = self._maybe_block(deff, dc, shot_type)
            if not blocked:
                miss = {"rim": "misses at the rim", "mid": "misses the jumper",
                        "three": "misses from deep"}[shot_type]
                self._log(off.team.tid, f"{shooter.short_name} {miss}")
            self._last_shot_live = True

    # -- shot helpers -------------------------------------------------------
    def _pick_shooter(self, off, oc, putback) -> int:
        conc = R.BALL_MOVEMENT_CONCENTRATION[off.team.tactics.ball_movement]
        if putback:
            weights = [w * (1.4 if p.position in ("PF", "C") else 1.0)
                       for w, p in zip(oc.rebound_w, oc.players)]
        else:
            # An iso set sharpens the usage curve so the ball finds the top option this trip.
            if self._iso_set:
                conc += 1.5
            weights = [u ** conc for u in oc.usage]
        return _weighted_index(self.rng, weights)

    def _pick_shot_type(self, shooter: Player, off, putback) -> str:
        if putback:
            return "rim"
        if self._three_bias and self.rng.chance(self._three_bias):
            return "three"
        r = shooter.ratings
        focus_rim, focus_three = R.OFF_FOCUS_SHOT[off.team.tactics.off_focus]
        rim = max(0.03, 0.36 + (r["finishing"] - 70) * 0.004 + (r["athleticism"] - 70) * 0.002
                  + focus_rim + self._rim_set)
        three = max(0.03, 0.32 + (r["three_point"] - 70) * 0.006 + focus_three)
        mid = max(0.04, 1.0 - rim - three)
        total = rim + three + mid
        roll = self.rng.random() * total
        if roll < rim:
            return "rim"
        if roll < rim + three:
            return "three"
        return "mid"

    def _shoot_fts_g(self, shooter: Player, n: int, off=None, deff=None):
        """Shoot ``n`` free throws, yielding a :class:`_SubBreak` before the final attempt of a
        multi-shot set (the legal sub window) when ``off``/``deff`` are supplied. Returns
        ``(makes, last_made)`` as the generator's value. The synchronous :meth:`_shoot_fts` and the
        and-one (``n == 1``) path pass no states and so never pause."""
        ft_pct = max(0.40, min(0.97, 0.05 + shooter.ratings["free_throw"] * 0.0095))
        line = self.result.line(shooter.pid)
        makes = 0
        last_made = False
        for i in range(n):
            if i == n - 1 and n >= 2 and off is not None:
                yield _SubBreak(off, deff)
            line.fta += 1
            if self.rng.chance(ft_pct):
                line.ftm += 1
                line.pts += 1
                makes += 1
                last_made = True
            else:
                last_made = False
        return makes, last_made

    def _shoot_fts(self, shooter: Player, n: int):
        """Synchronous free throws (no sub window) for the and-one path and non-coached sims."""
        gen = self._shoot_fts_g(shooter, n)
        try:
            while True:
                next(gen)
        except StopIteration as done:
            return done.value

    def _maybe_assist(self, off, oc, shooter: Player, shot_type: str) -> Optional[Player]:
        base = {"three": 0.82, "mid": 0.45, "rim": 0.50}[shot_type]
        base += R.BALL_MOVEMENT_ASSIST[off.team.tactics.ball_movement]
        base = max(0.05, min(0.95, base))
        if not self.rng.chance(base):
            return None
        others = [(i, p) for i, p in enumerate(oc.players) if p.pid != shooter.pid]
        if not others:
            return None
        weights = [oc.passing_w[i] for i, _ in others]
        idx = _weighted_index(self.rng, weights)
        passer = others[idx][1]
        self.result.line(passer.pid).ast += 1
        return passer

    def _maybe_block(self, deff, dc, shot_type: str) -> bool:
        block_p = max(0.0, (dc.block_anchor - 62) * 0.004)
        if shot_type == "mid":
            block_p *= 0.4
        block_p = min(0.16, block_p)
        if self.rng.chance(block_p):
            idx = _weighted_index(self.rng, [p.ratings["block"] for p in dc.players])
            blocker = dc.players[idx]
            self.result.line(blocker.pid).blk += 1
            self._log(deff.team.tid, f"{blocker.short_name} blocks the shot")
            return True
        return False

    def _commit_foul(self, deff, dc) -> Player:
        idx = _weighted_index(self.rng, dc.foul_w)
        fouler = dc.players[idx]
        self.result.line(fouler.pid).pf += 1
        deff.fouls[fouler.pid] = deff.fouls.get(fouler.pid, 0) + 1
        deff.period_fouls += 1
        if deff.fouls[fouler.pid] >= FOUL_OUT:
            deff.unavailable.add(fouler.pid)
            if fouler.pid in deff.on_court:
                deff.choose_lineup(self.game_secs, clutch=self._clutch_for(deff))
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
            self._log(team.team.tid, f"{rebounder.short_name} grabs the offensive board")
        else:
            self.result.line(rebounder.pid).dreb += 1
            self._log(team.team.tid, f"{rebounder.short_name} grabs the rebound")

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
                state.choose_lineup(self.game_secs, clutch=self._clutch_for(state))
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


def simulate_game(world, home: Team, away: Team, *, collect_pbp: bool = False,
                  coach: Optional[Coach] = None, coach_tid: Optional[int] = None) -> GameResult:
    """Convenience wrapper: simulate one game and return its result."""
    return GameSim(world, home, away, collect_pbp=collect_pbp,
                   coach=coach, coach_tid=coach_tid).play()
