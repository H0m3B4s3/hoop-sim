"""FastAPI backend for HoopR.

Each route mirrors a terminal action in ``hoopr.ui`` and calls the *same* engine functions
(``sim``/``systems``), so the web GUI and the CLI drive an identical game. State lives in
``hoopr.web.session`` (one World per browser session); persistence reuses ``hoopr.save.store``.
"""
from __future__ import annotations

import os
import random
import webbrowser
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hoopr.config import ROSTER_MIN, SEASON_PRESETS
from hoopr.models.league import Game, Phase
from hoopr.models.team import auto_set_lineup
from hoopr.models.tactics import SETTINGS
from hoopr.models.world import World
from hoopr.sim import playoffs as P
from hoopr.sim import season as S
from hoopr.sim.coach import Coach, CoachOrders
from hoopr.sim.engine import GameSim
from hoopr.systems import cap, draft_system as D, freeagency, offseason, trades
from hoopr.web import serializers as ser
from hoopr.web.session import SESSIONS

app = FastAPI(title="HoopR", version="0.1.0")

_COOKIE = "hoopr_sid"


# ---------------------------------------------------------------------------
# Session plumbing
# ---------------------------------------------------------------------------
def _sid(response: Response, hoopr_sid: Optional[str] = Cookie(default=None)) -> str:
    """Ensure every request carries a session id, minting one on first contact."""
    sid = hoopr_sid or SESSIONS.new_session()
    if hoopr_sid is None:
        response.set_cookie(_COOKIE, sid, httponly=True, samesite="lax")
    return sid


def _world(sid: str) -> World:
    try:
        return SESSIONS.require(sid)
    except KeyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _user_team(world: World):
    team = world.user_team
    if team is None:
        raise HTTPException(status_code=409, detail="No user team selected.")
    return team


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class NewCareer(BaseModel):
    league: str = "nba"                 # "nba" | "college"
    preset: str = "Standard"            # NBA season length
    economy: str = "nil"               # college economy: "scholarship" | "nil"
    seed: Optional[int] = None


class SlotBody(BaseModel):
    slot: str


class SignBody(BaseModel):
    pid: int
    salary: Optional[int] = None
    years: Optional[int] = None


class ExtendBody(BaseModel):
    pid: int
    salary: Optional[int] = None
    add_years: Optional[int] = None


class TradeBody(BaseModel):
    partner_tid: int
    user_sends: List[int] = []
    partner_sends: List[int] = []
    user_picks: List[List[int]] = []      # pick keys [year, round, original_tid]
    partner_picks: List[List[int]] = []


class WaiveBody(BaseModel):
    pid: int


class BlockBody(BaseModel):
    pid: int
    on: bool


class OfferBody(BaseModel):
    id: int


class SolicitBody(BaseModel):
    pids: List[int] = []


class LineupBody(BaseModel):
    starters: Optional[List[int]] = None   # None -> revert to automatic
    auto: bool = False


class TacticBody(BaseModel):
    key: str
    value: str


class DraftPickBody(BaseModel):
    pid: Optional[int] = None              # None -> best available


class CoachOrdersBody(BaseModel):
    """One possession's crunch-time decision from the browser."""
    timeout: bool = False
    tempo: str = "normal"                  # normal | hold | quick (offense)
    defensive_foul: str = "auto"           # auto | foul | no (defense)
    lineup: Optional[List[int]] = None     # new on-court five, or None to leave it


# ---------------------------------------------------------------------------
# State, career, saves
# ---------------------------------------------------------------------------
@app.get("/api/state")
def state(sid: str = Depends(_sid)):
    world = SESSIONS.get(sid)
    if world is None:
        return {"active": False, "presets": list(SEASON_PRESETS.keys()),
                "saves": SESSIONS.list_saves()}
    return {"active": True, "needs_team": world.user_team_id is None,
            "summary": ser.world_summary(world)}


@app.post("/api/career/new")
def career_new(body: NewCareer, sid: str = Depends(_sid)):
    seed = body.seed if body.seed is not None else random.randrange(1 << 30)
    if body.league == "college":
        from hoopr.gen.collegegen import build_college_world
        world = build_college_world(seed=seed, economy=body.economy)
    else:
        preset = body.preset if body.preset in SEASON_PRESETS else "Standard"
        from hoopr.gen.leaguegen import build_world
        world = build_world(seed=seed, season_preset=preset)
    SESSIONS.set(sid, world)
    return {"seed": seed, "needs_team": True, "summary": ser.world_summary(world)}


@app.post("/api/career/team/{tid}")
def career_team(tid: int, sid: str = Depends(_sid)):
    world = _world(sid)
    if tid not in world.teams:
        raise HTTPException(status_code=404, detail="Unknown team.")
    world.user_team_id = tid
    S.start_season(world)
    SESSIONS.autosave(sid)
    return ser.world_summary(world)


@app.get("/api/saves")
def saves(sid: str = Depends(_sid)):
    return {"saves": SESSIONS.list_saves()}


@app.post("/api/save")
def save(body: SlotBody, sid: str = Depends(_sid)):
    _world(sid)
    path = SESSIONS.save(sid, body.slot)
    return {"saved": os.path.basename(path)}


@app.post("/api/load")
def load(body: SlotBody, sid: str = Depends(_sid)):
    try:
        world = SESSIONS.load(sid, body.slot)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Failed to load: {exc}") from exc
    return ser.world_summary(world)


# ---------------------------------------------------------------------------
# Read-only views
# ---------------------------------------------------------------------------
@app.get("/api/teams/{tid}/roster")
def roster(tid: int, sid: str = Depends(_sid)):
    world = _world(sid)
    team = world.find_team(tid)
    if team is None:
        raise HTTPException(status_code=404, detail="Unknown team.")
    return ser.roster_view(world, team)


@app.get("/api/standings")
def standings(sid: str = Depends(_sid)):
    return ser.standings_view(_world(sid))


@app.get("/api/leaders")
def leaders(sid: str = Depends(_sid)):
    return ser.leaders_view(_world(sid))


@app.get("/api/finances")
def finances(sid: str = Depends(_sid)):
    world = _world(sid)
    return ser.finances_view(world, _user_team(world))


@app.get("/api/freeagents")
def free_agents(sid: str = Depends(_sid)):
    return ser.free_agents_view(_world(sid))


@app.get("/api/scouting")
def scouting(sid: str = Depends(_sid)):
    return ser.scouting_view(_world(sid))


@app.get("/api/history")
def history(sid: str = Depends(_sid)):
    world = _world(sid)
    return {"history": ser.history_view(world)}


@app.get("/api/teams/{tid}/depth-chart")
def depth_chart(tid: int, sid: str = Depends(_sid)):
    world = _world(sid)
    team = world.find_team(tid)
    if team is None:
        raise HTTPException(status_code=404, detail="Unknown team.")
    return ser.depth_chart_view(world, team)


@app.get("/api/teams/{tid}/picks")
def team_picks(tid: int, sid: str = Depends(_sid)):
    world = _world(sid)
    if world.find_team(tid) is None:
        raise HTTPException(status_code=404, detail="Unknown team.")
    return {"tid": tid, "picks": [ser.pick_view(world, p) for p in world.picks_owned_by(tid)]}


@app.get("/api/teams/{tid}/trade-block")
def trade_block(tid: int, sid: str = Depends(_sid)):
    world = _world(sid)
    team = world.find_team(tid)
    if team is None:
        raise HTTPException(status_code=404, detail="Unknown team.")
    return {"tid": tid, "pids": trades.team_trade_block(world, team)}


@app.get("/api/players/{pid}")
def player(pid: int, sid: str = Depends(_sid)):
    world = _world(sid)
    p = world.players.get(pid)
    if p is None:
        raise HTTPException(status_code=404, detail="Unknown player.")
    return ser.player_detail(world, p)


# ---------------------------------------------------------------------------
# Simulation (regular season) — mirrors ui.app_ui._play_user_game / _sim_span
# ---------------------------------------------------------------------------
# -- interactive crunch-time coaching ---------------------------------------
class _WebCoach(Coach):
    """Server-side coach for an in-progress game: it never decides (the browser does, out of
    band) but collects the play-by-play of each coached possession so the API can stream it."""
    def __init__(self) -> None:
        self.events: list = []

    def narrate(self, events) -> None:
        self.events.extend(events)

    def drain(self) -> list:
        out, self.events = self.events, []
        return out


@dataclass
class _LiveGame:
    sim: GameSim
    driver: object
    coach: _WebCoach
    game: Game
    finalize: object        # (world, result) -> dict of mode-specific "final" payload fields


_LIVE: Dict[str, _LiveGame] = {}


def _play_other_games_today(world: World) -> None:
    """Sim every non-user game on the current day; the user's is played interactively."""
    uid = world.user_team_id
    for g in S.games_on_day(world, world.day):
        if uid is None or not g.involves(uid):
            S.sim_one(world, g)


def _start_live_game(world: World, sid: str, game: Game, finalize) -> dict:
    """Set up the user's game for interactive coaching and pump to the first decision/final."""
    home, away = world.teams[game.home], world.teams[game.away]
    auto_set_lineup(home, world.players)
    auto_set_lineup(away, world.players)
    coach = _WebCoach()
    sim = GameSim(world, home, away, collect_pbp=True, coach=coach,
                  coach_tid=world.user_team_id)
    live = _LIVE[sid] = _LiveGame(sim=sim, driver=sim.coach_session(), coach=coach,
                                  game=game, finalize=finalize)
    return _pump(world, sid, live, orders=None)


def _pump(world: World, sid: str, live: _LiveGame, orders: Optional[CoachOrders]) -> dict:
    """Advance the live game to its next decision (or the final), returning a JSON payload."""
    try:
        view = next(live.driver) if orders is None else live.driver.send(orders)
    except StopIteration:
        return _finish_live_game(world, sid, live)
    return {
        "status": "decision",
        "events": [ser.coach_event_view(world, e) for e in live.coach.drain()],
        "decision": ser.coach_view_json(world, view),
        "summary": ser.world_summary(world),
    }


def _finish_live_game(world: World, sid: str, live: _LiveGame) -> dict:
    events = [ser.coach_event_view(world, e) for e in live.coach.drain()]
    extra = live.finalize(world, live.sim.result)   # applies result + advances structures
    _LIVE.pop(sid, None)
    SESSIONS.autosave(sid)
    return {
        "status": "final",
        "played": True,
        "events": events,
        "result": ser.game_result_view(world, live.sim.result),
        **extra,
    }


@app.post("/api/sim/game")
def sim_game(watch: bool = False, sid: str = Depends(_sid)):
    world = _world(sid)
    game = S.user_next_game(world)
    if game is None:
        while not S.regular_season_complete(world):
            S.advance_one_day(world)
        SESSIONS.autosave(sid)
        return {"played": False, "message": "Your regular season is complete.",
                "summary": ser.world_summary(world)}
    while world.day < game.day:
        S.advance_one_day(world)

    if watch:
        # Interactive: play the rest of today's slate, then coach the user's game live.
        _play_other_games_today(world)

        def finalize(w: World, result, _game=game) -> dict:
            S._apply_result(w, _game, result, is_playoff=False)
            S._heal_injuries(w)
            w.day += 1
            return {"summary": ser.world_summary(w), "new_offers": trades.refresh_offers(w)}

        return _start_live_game(world, sid, game, finalize)

    _, user_result = S.advance_one_day(world, watch_user=False)
    new_offers = trades.refresh_offers(world)
    SESSIONS.autosave(sid)
    out = {"played": True, "summary": ser.world_summary(world), "new_offers": new_offers}
    if user_result is not None:
        out["result"] = ser.game_result_view(world, user_result)
    return out


@app.post("/api/sim/coach")
def sim_coach(body: CoachOrdersBody, sid: str = Depends(_sid)):
    world = _world(sid)
    live = _LIVE.get(sid)
    if live is None:
        raise HTTPException(status_code=409, detail="No game is currently in progress.")
    orders = CoachOrders(timeout=body.timeout, tempo=body.tempo,
                         defensive_foul=body.defensive_foul, lineup=body.lineup)
    return _pump(world, sid, live, orders=orders)


@app.post("/api/sim/week")
def sim_week(days: int = 4, sid: str = Depends(_sid)):
    world = _world(sid)
    uid = world.user_team_id
    user_games = []
    for _ in range(max(1, days)):
        if S.regular_season_complete(world):
            break
        results, _ = S.advance_one_day(world)
        user_games += [g for g, _ in results if g.involves(uid)]
    new_offers = trades.refresh_offers(world)
    SESSIONS.autosave(sid)
    return {"results": [ser.schedule_result(world, g) for g in user_games],
            "summary": ser.world_summary(world),
            "season_complete": S.regular_season_complete(world),
            "new_offers": new_offers}


@app.post("/api/sim/advance-day")
def advance_day(sid: str = Depends(_sid)):
    world = _world(sid)
    uid = world.user_team_id
    results, _ = S.advance_one_day(world)
    new_offers = trades.refresh_offers(world)
    SESSIONS.autosave(sid)
    return {"results": [ser.schedule_result(world, g) for g, _ in results if g.involves(uid)],
            "summary": ser.world_summary(world),
            "season_complete": S.regular_season_complete(world),
            "new_offers": new_offers}


# ---------------------------------------------------------------------------
# Playoffs — mirrors ui.app_ui._enter_playoffs / _advance_playoffs
# ---------------------------------------------------------------------------
@app.get("/api/playoffs")
def playoffs(sid: str = Depends(_sid)):
    world = _world(sid)
    return {"bracket": world.bracket, "complete": P.playoffs_complete(world),
            "champion": P.champion(world)}


@app.post("/api/playoffs/start")
def playoffs_start(sid: str = Depends(_sid)):
    world = _world(sid)
    log = P.start_playoffs(world)
    SESSIONS.autosave(sid)
    return {"log": log, "bracket": world.bracket}


def _playoff_slate_out(world: World, results) -> dict:
    return {"bracket": world.bracket, "complete": P.playoffs_complete(world),
            "champion": P.champion(world),
            "slate": [{"status": P.series_status(world, s),
                       "away": world.find_team(r.away_tid).abbrev,
                       "home": world.find_team(r.home_tid).abbrev,
                       "away_score": r.away_score, "home_score": r.home_score}
                      for s, r in results]}


@app.post("/api/playoffs/advance")
def playoffs_advance(watch: bool = False, sid: str = Depends(_sid)):
    world = _world(sid)
    if watch:
        series = P.user_series(world)
        if series is not None:
            # Play the rest of this round's slate, then coach the user's series game live.
            other = P.play_nonuser_slate(world)
            game = P.start_user_series_game(world, series)

            def finalize(w: World, result, _s=series, _game=game, _other=other) -> dict:
                P.finish_user_series_game(w, _s, _game, result)
                out = _playoff_slate_out(w, list(_other))
                out["summary"] = ser.world_summary(w)
                return out

            return _start_live_game(world, sid, game, finalize)

    results, user_result = P.advance_playoff_slate(world, watch_user=watch)
    SESSIONS.autosave(sid)
    out = _playoff_slate_out(world, results)
    if watch and user_result is not None:
        out["result"] = ser.game_result_view(world, user_result)
    return out


# ---------------------------------------------------------------------------
# Front office — trades, signings, extensions (mirrors ui.screens.*)
# ---------------------------------------------------------------------------
def _offer_from_body(world: World, body: TradeBody) -> "trades.TradeOffer":
    return trades.TradeOffer(world.user_team_id, body.partner_tid,
                             list(body.user_sends), list(body.partner_sends),
                             [tuple(k) for k in body.user_picks],
                             [tuple(k) for k in body.partner_picks])


@app.post("/api/trade/validate")
def trade_validate(body: TradeBody, sid: str = Depends(_sid)):
    world = _world(sid)
    offer = _offer_from_body(world, body)
    legal, why = trades.validate_trade(world, offer)
    accepts, ai_why = (trades.ai_evaluates(world, offer, body.partner_tid)
                       if legal else (False, "Trade is not legal."))
    return {"legal": legal, "legal_reason": why, "accepts": accepts, "ai_reason": ai_why}


@app.post("/api/trade/execute")
def trade_execute(body: TradeBody, sid: str = Depends(_sid)):
    world = _world(sid)
    offer = _offer_from_body(world, body)
    legal, why = trades.validate_trade(world, offer)
    if not legal:
        raise HTTPException(status_code=400, detail=why)
    accepts, ai_why = trades.ai_evaluates(world, offer, body.partner_tid)
    if not accepts:
        return {"executed": False, "reason": ai_why}
    trades.execute_trade(world, offer)
    SESSIONS.autosave(sid)
    return {"executed": True, "summary": ser.world_summary(world)}


@app.post("/api/trade/solicit")
def trade_solicit(body: SolicitBody, sid: str = Depends(_sid)):
    """Shop the user's player(s) and return the offers interested teams would make."""
    world = _world(sid)
    _user_team(world)
    offers = trades.solicit_offers(world, list(body.pids))
    return {"offers": [ser.solicited_offer_view(world, o) for o in offers]}


@app.post("/api/trade/accept")
def trade_accept(body: TradeBody, sid: str = Depends(_sid)):
    """Accept a solicited offer the AI already proposed — legality-checked, no re-evaluation."""
    world = _world(sid)
    offer = _offer_from_body(world, body)
    legal, why = trades.validate_trade(world, offer)
    if not legal:
        raise HTTPException(status_code=400, detail=why)
    trades.execute_trade(world, offer)
    SESSIONS.autosave(sid)
    return {"executed": True, "summary": ser.world_summary(world)}


@app.post("/api/sign")
def sign(body: SignBody, sid: str = Depends(_sid)):
    world = _world(sid)
    team = _user_team(world)
    p = world.players.get(body.pid)
    if p is None or not p.is_free_agent:
        raise HTTPException(status_code=400, detail="Player is not a free agent.")
    salary, years = freeagency.offer_for(world, team, p)
    salary = body.salary if body.salary is not None else salary
    years = body.years if body.years is not None else years
    ok, why = freeagency.sign_free_agent(world, team, body.pid, salary, years)
    if ok:
        SESSIONS.autosave(sid)
    return {"signed": ok, "reason": why, "summary": ser.world_summary(world)}


@app.post("/api/extend")
def extend(body: ExtendBody, sid: str = Depends(_sid)):
    world = _world(sid)
    team = _user_team(world)
    p = world.players.get(body.pid)
    if p is None:
        raise HTTPException(status_code=404, detail="Unknown player.")
    salary, add_years = cap.extension_offer(world, p)
    salary = body.salary if body.salary is not None else salary
    add_years = body.add_years if body.add_years is not None else add_years
    ok, why = cap.extend_contract(world, team, body.pid, salary, add_years)
    if ok:
        SESSIONS.autosave(sid)
    return {"extended": ok, "reason": why, "summary": ser.world_summary(world)}


@app.post("/api/waive")
def waive(body: WaiveBody, sid: str = Depends(_sid)):
    world = _world(sid)
    team = _user_team(world)
    if body.pid not in team.roster:
        raise HTTPException(status_code=400, detail="That player is not on your roster.")
    if len(team.roster) <= ROSTER_MIN:
        raise HTTPException(status_code=400,
                            detail=f"Roster is at the minimum ({ROSTER_MIN}); "
                                   "sign or trade before waiving.")
    p = world.players[body.pid]
    world.release_player(body.pid)
    if body.pid in team.block_list:
        team.block_list.remove(body.pid)
    auto_set_lineup(team, world.players)
    SESSIONS.autosave(sid)
    return {"waived": True, "name": p.name, "summary": ser.world_summary(world)}


# ---------------------------------------------------------------------------
# Trade block & AI-initiated offers (inbox)
# ---------------------------------------------------------------------------
@app.post("/api/block")
def set_block(body: BlockBody, sid: str = Depends(_sid)):
    world = _world(sid)
    team = _user_team(world)
    if body.pid not in team.roster:
        raise HTTPException(status_code=400, detail="That player is not on your roster.")
    if body.on and body.pid not in team.block_list:
        team.block_list.append(body.pid)
    elif not body.on and body.pid in team.block_list:
        team.block_list.remove(body.pid)
    SESSIONS.autosave(sid)
    return {"pid": body.pid, "on_block": body.pid in team.block_list}


@app.get("/api/offers")
def offers(sid: str = Depends(_sid)):
    world = _world(sid)
    _user_team(world)
    return {"offers": [ser.offer_view(world, o) for o in world.trade_offers]}


@app.post("/api/offers/accept")
def offers_accept(body: OfferBody, sid: str = Depends(_sid)):
    world = _world(sid)
    _user_team(world)
    ok, why = trades.accept_offer(world, body.id)
    SESSIONS.autosave(sid)
    return {"executed": ok, "reason": why, "summary": ser.world_summary(world)}


@app.post("/api/offers/decline")
def offers_decline(body: OfferBody, sid: str = Depends(_sid)):
    world = _world(sid)
    _user_team(world)
    trades.decline_offer(world, body.id)
    SESSIONS.autosave(sid)
    return {"declined": True, "summary": ser.world_summary(world)}


# ---------------------------------------------------------------------------
# Lineup & tactics (mirrors ui.screens.lineup / tactics)
# ---------------------------------------------------------------------------
@app.post("/api/lineup")
def set_lineup(body: LineupBody, sid: str = Depends(_sid)):
    world = _world(sid)
    team = _user_team(world)
    if body.auto or body.starters is None:
        team.auto_lineup = True
    else:
        ids = [pid for pid in body.starters if pid in team.roster][:5]
        if len(ids) != 5:
            raise HTTPException(status_code=400, detail="Need exactly five players on the roster.")
        team.starters = ids
        team.auto_lineup = False
    auto_set_lineup(team, world.players)
    SESSIONS.autosave(sid)
    return ser.roster_view(world, team)


@app.get("/api/tactics")
def get_tactics(sid: str = Depends(_sid)):
    world = _world(sid)
    team = _user_team(world)
    return {"tactics": [{"key": k, "label": label, "value": value, "options": list(SETTINGS[k])}
                        for k, label, value in team.tactics.items()]}


@app.post("/api/tactics")
def set_tactic(body: TacticBody, sid: str = Depends(_sid)):
    world = _world(sid)
    team = _user_team(world)
    if body.key not in SETTINGS or body.value not in SETTINGS[body.key]:
        raise HTTPException(status_code=400, detail="Invalid tactic setting.")
    setattr(team.tactics, body.key, body.value)
    SESSIONS.autosave(sid)
    return get_tactics(sid)


# ---------------------------------------------------------------------------
# Offseason: draft & free agency (mirrors ui.app_ui._run_offseason)
# ---------------------------------------------------------------------------
@app.post("/api/offseason/pre-draft")
def offseason_pre_draft(sid: str = Depends(_sid)):
    world = _world(sid)
    champ = P.champion(world)
    # Idempotent: once the draft class exists the offseason has already begun this year, so
    # never re-run pre_draft (which would age, retire, and expire contracts a second time).
    if world.draft_class is not None:
        return {"summary": {"new_fas": 0, "retired": 0}, "champion": champ, "resumed": True}
    summary = offseason.pre_draft(world, champ)
    D.setup_draft(world)
    SESSIONS.autosave(sid)
    latest = world.history[-1].get("awards") if world.history else None
    return {"summary": summary, "champion": champ, "awards": latest}


def _draft_board(world: World, dc, limit: int = 14):
    remaining = sorted(dc.remaining_prospects(),
                       key=lambda pid: D.prospect_rank(world.players[pid]), reverse=True)[:limit]
    return [{"pid": pid, **{k: ser.player_row(world, world.players[pid])[k]
                            for k in ("name", "position", "age", "overall", "potential",
                                      "archetype")}}
            for pid in remaining]


@app.get("/api/draft/board")
def draft_board(sid: str = Depends(_sid)):
    """Auto-advance AI picks until the user is on the clock (or the draft ends)."""
    world = _world(sid)
    dc = world.draft_class
    if dc is None:
        raise HTTPException(status_code=409, detail="Draft has not been set up.")
    recent = []
    while not dc.complete and dc.team_on_clock() != world.user_team_id:
        pick_no = dc.current_pick
        tid = dc.team_on_clock()
        pid = D.ai_pick(world)
        p = world.players[pid]
        recent.append({"pick": pick_no, "team": world.teams[tid].abbrev,
                       "player": p.name, "position": p.position, "overall": p.overall})
    if dc.complete:
        D.undrafted_to_free_agents(world)
        world.phase = Phase.FREE_AGENCY        # advance the offseason past the draft
        SESSIONS.autosave(sid)
        return {"complete": True, "recent": recent, "summary": ser.world_summary(world)}
    return {"complete": False, "on_clock": True, "pick": dc.current_pick,
            "recent": recent, "board": _draft_board(world, dc)}


@app.post("/api/draft/pick")
def draft_pick(body: DraftPickBody, sid: str = Depends(_sid)):
    world = _world(sid)
    dc = world.draft_class
    if dc is None or dc.complete:
        raise HTTPException(status_code=409, detail="No active draft.")
    if dc.team_on_clock() != world.user_team_id:
        raise HTTPException(status_code=409, detail="You are not on the clock.")
    pid = body.pid if body.pid is not None else D.best_available(world)
    pick_no = dc.current_pick
    D.make_pick(world, pid)
    p = world.players[pid]
    SESSIONS.autosave(sid)
    return {"picked": {"pick": pick_no, "pid": pid, "name": p.name,
                       "position": p.position, "overall": p.overall,
                       "potential": p.scouted_potential()}}


@app.post("/api/offseason/run-fa")
def offseason_run_fa(sid: str = Depends(_sid)):
    world = _world(sid)
    offseason.enforce_roster_max(world)
    result = freeagency.run_free_agency(world)
    SESSIONS.autosave(sid)
    return {"result": result}


@app.post("/api/offseason/finish")
def offseason_finish(sid: str = Depends(_sid)):
    world = _world(sid)
    offseason.post_offseason(world)
    SESSIONS.autosave(sid)
    return ser.world_summary(world)


# ---------------------------------------------------------------------------
# Static frontend (built SPA), mounted last so /api/* wins.
# ---------------------------------------------------------------------------
_DIST = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="static")


def run() -> None:
    """Console entry point: serve the app and open a browser."""
    import uvicorn

    host, port = "127.0.0.1", 8000
    if os.environ.get("HOOPR_NO_BROWSER") != "1":
        try:
            webbrowser.open(f"http://{host}:{port}")
        except Exception:  # noqa: BLE001
            pass
    uvicorn.run("hoopr.web.app:app", host=host, port=port, reload=False)
