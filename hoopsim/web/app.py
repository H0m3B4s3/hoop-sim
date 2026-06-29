"""FastAPI backend for HoopSim.

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

from hoopsim.config import ROSTER_MIN, SEASON_PRESETS
from hoopsim.models.league import Game, Phase
from hoopsim.models.team import auto_set_lineup
from hoopsim.models.tactics import SETTINGS
from hoopsim.models.world import World
from hoopsim.sim import college_tourney as CT
from hoopsim.sim import playoffs as P
from hoopsim.sim import season as S
from hoopsim.sim.coach import Coach, CoachOrders
from hoopsim.sim.engine import GameSim
from hoopsim.systems import (cap, college_offseason as CO, collegefin, draft_system as D,
                           freeagency, offseason, recruiting, trades)
from hoopsim.web import serializers as ser
from hoopsim.web.session import SESSIONS

app = FastAPI(title="HoopSim", version="0.1.0")

_COOKIE = "hoopsim_sid"


# ---------------------------------------------------------------------------
# Session plumbing
# ---------------------------------------------------------------------------
def _sid(response: Response, hoopsim_sid: Optional[str] = Cookie(default=None)) -> str:
    """Ensure every request carries a session id, minting one on first contact."""
    sid = hoopsim_sid or SESSIONS.new_session()
    if hoopsim_sid is None:
        response.set_cookie(_COOKIE, sid, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 365)
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


class RotationBody(BaseModel):
    rotation: Optional[List[int]] = None   # pids beyond the starters; None -> revert to automatic


class TacticBody(BaseModel):
    key: str
    value: str


class DraftPickBody(BaseModel):
    pid: Optional[int] = None              # None -> best available


class ShopPickBody(BaseModel):
    key: List[int]                         # pick key [year, round, original_tid] to shop


class FogBody(BaseModel):
    enabled: bool                          # toggle potential fog of war


class RecruitSignBody(BaseModel):
    """College Signing Day: recruit pid -> NIL amount (NIL mode) or any truthy value
    (scholarship mode means 'offer extended'). Keys arrive as strings over JSON."""
    offers: Dict[int, int] = {}


class CoachOrdersBody(BaseModel):
    """One possession's crunch-time decision from the browser."""
    timeout: bool = False
    tempo: str = "normal"                  # normal | bleed | hold | quick3 (offense)
    offensive_set: str = "motion"          # motion | iso | inside | spread (offense)
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
                "saves": SESSIONS.list_saves(sid)}
    return {"active": True, "needs_team": world.user_team_id is None,
            "summary": ser.world_summary(world)}


@app.post("/api/career/new")
def career_new(body: NewCareer, sid: str = Depends(_sid)):
    seed = body.seed if body.seed is not None else random.randrange(1 << 30)
    if body.league == "college":
        from hoopsim.gen.collegegen import build_college_world
        world = build_college_world(seed=seed, economy=body.economy)
    else:
        preset = body.preset if body.preset in SEASON_PRESETS else "Standard"
        from hoopsim.gen.leaguegen import build_world
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
    return {"saves": SESSIONS.list_saves(sid)}


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


@app.get("/api/power")
def power(sid: str = Depends(_sid)):
    return ser.power_view(_world(sid))


@app.get("/api/fog")
def fog_get():
    from hoopsim.systems import scouting as SC
    return {"enabled": SC.fog_enabled()}


@app.post("/api/fog")
def fog_set(body: FogBody):
    from hoopsim.systems import scouting as SC
    SC.set_fog(body.enabled)
    return {"enabled": SC.fog_enabled()}


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
                         offensive_set=body.offensive_set,
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
    if world.mode == "college":
        return {"bracket": world.bracket, "complete": CT.college_postseason_complete(world),
                "champion": CT.national_champion(world)}
    return {"bracket": world.bracket, "complete": P.playoffs_complete(world),
            "champion": P.champion(world)}


@app.post("/api/playoffs/start")
def playoffs_start(sid: str = Depends(_sid)):
    world = _world(sid)
    log = CT.start_college_postseason(world) if world.mode == "college" \
        else P.start_playoffs(world)
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


def _college_slate_out(world: World, results) -> dict:
    def _status(m) -> str:
        a, b = world.find_team(m["a"]), world.find_team(m["b"])
        return f"{a.abbrev} {m['a_score']}-{m['b_score']} {b.abbrev}"
    return {"bracket": world.bracket, "complete": CT.college_postseason_complete(world),
            "champion": CT.national_champion(world),
            "slate": [{"status": _status(m),
                       "away": world.find_team(r.away_tid).abbrev,
                       "home": world.find_team(r.home_tid).abbrev,
                       "away_score": r.away_score, "home_score": r.home_score}
                      for m, r in results]}


@app.post("/api/playoffs/advance")
def playoffs_advance(watch: bool = False, sid: str = Depends(_sid)):
    world = _world(sid)
    if world.mode == "college":
        return _college_advance(world, sid, watch)
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


def _college_advance(world: World, sid: str, watch: bool) -> dict:
    """College postseason advance: conference tournaments then the national tournament."""
    if watch:
        match = CT.user_match(world)
        if match is not None:
            # Play the rest of this round's slate, then coach the user's game live.
            other = CT.play_nonuser_college_slate(world)
            game = CT.start_user_college_game(world, match)

            def finalize(w: World, result, _m=match, _game=game, _other=other) -> dict:
                CT.finish_user_college_game(w, _m, _game, result)
                out = _college_slate_out(w, list(_other))
                out["summary"] = ser.world_summary(w)
                return out

            return _start_live_game(world, sid, game, finalize)

    results, user_result = CT.advance_college_slate(world, watch_user=watch)
    SESSIONS.autosave(sid)
    out = _college_slate_out(world, results)
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
    schedule = world.dead_money_schedule(p.contract)
    world.release_player(body.pid)
    if body.pid in team.block_list:
        team.block_list.remove(body.pid)
    auto_set_lineup(team, world.players)
    SESSIONS.autosave(sid)
    return {"waived": True, "name": p.name,
            "dead_money": sum(schedule), "dead_money_years": len(schedule),
            "summary": ser.world_summary(world)}


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


@app.post("/api/rotation")
def set_rotation(body: RotationBody, sid: str = Depends(_sid)):
    """Pin which non-starters draw minutes (Rotation vs End of Bench), or revert to automatic."""
    from hoopsim.models.team import MAX_ROTATION
    world = _world(sid)
    team = _user_team(world)
    if body.rotation is None:
        team.rotation = []                 # back to the head coach's automatic rotation
    else:
        starters = set(team.starters)
        seen: set = set()
        ids = []
        for pid in body.rotation:          # de-dupe, drop starters/strangers, keep order
            if pid in team.roster and pid not in starters and pid not in seen:
                seen.add(pid)
                ids.append(pid)
        team.rotation = ids[:max(0, MAX_ROTATION - len(team.starters))]
    auto_set_lineup(team, world.players)
    SESSIONS.autosave(sid)
    return ser.roster_view(world, team)


@app.get("/api/tactics")
def get_tactics(sid: str = Depends(_sid)):
    world = _world(sid)
    team = _user_team(world)
    coach = None
    if team.coach is not None:
        prof = team.coach.profile
        coach = {"name": team.coach.name, "archetype": prof.key,
                 "label": prof.label, "blurb": prof.blurb}
    return {"coach": coach,
            "tactics": [{"key": k, "label": label, "value": value, "options": list(SETTINGS[k])}
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
        return {"summary": {"new_fas": 0, "retired": 0, "resigned": 0},
                "champion": champ, "resumed": True}
    summary = offseason.pre_draft(world, champ)
    D.setup_draft(world)
    SESSIONS.autosave(sid)
    latest = world.history[-1].get("awards") if world.history else None
    return {"summary": summary, "champion": champ, "awards": latest}


def _draft_board(world: World, dc, limit: int = 30):
    remaining = sorted(dc.remaining_prospects(),
                       key=lambda pid: D.prospect_rank(world.players[pid]), reverse=True)[:limit]
    return [ser.prospect_row(world, world.players[pid]) for pid in remaining]


def _user_draft_picks(world: World):
    """The user's tradeable *future* picks, soonest first — what they can shop on the clock.

    The current draft's order is already fixed, so only later years are tradeable here."""
    user = world.user_team
    if user is None:
        return []
    cur = world.draft_class.year if world.draft_class else world.season_year
    picks = sorted((pk for pk in world.picks_owned_by(user.tid) if pk.year > cur),
                   key=lambda pk: (pk.year, pk.round))
    return [ser.pick_view(world, pk) for pk in picks]


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
            "recent": recent, "board": _draft_board(world, dc),
            "my_picks": _user_draft_picks(world)}


@app.post("/api/draft/shop-pick")
def draft_shop_pick(body: ShopPickBody, sid: str = Depends(_sid)):
    """Shop one of the user's draft picks without leaving the draft room."""
    world = _world(sid)
    _user_team(world)
    offers = trades.solicit_pick_offers(world, tuple(body.key))
    return {"offers": [ser.solicited_offer_view(world, o) for o in offers]}


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


@app.post("/api/offseason/fa/start")
def offseason_fa_start(sid: str = Depends(_sid)):
    """Open the tiered free-agent market (idempotent: resuming mid-market keeps the open wave)."""
    world = _world(sid)
    offseason.enforce_roster_max(world)
    if world.fa_wave is None:
        freeagency.start_fa_market(world)
        SESSIONS.autosave(sid)
    return ser.fa_wave_view(world)


@app.post("/api/offseason/fa/advance")
def offseason_fa_advance(sid: str = Depends(_sid)):
    """User is done with the open wave: rival GMs bid on it, then the next wave opens."""
    world = _world(sid)
    if world.fa_wave is None:
        freeagency.start_fa_market(world)
    wave = world.fa_wave
    result = freeagency.run_fa_wave(world)
    more = freeagency.advance_fa_wave(world)
    SESSIONS.autosave(sid)
    return {"signings": result["signings"], "wave": wave + 1, "done": not more,
            "next": ser.fa_wave_view(world)}


@app.post("/api/offseason/run-fa")
def offseason_run_fa(sid: str = Depends(_sid)):
    """Headless fallback: resolve the whole tiered market in one pass (AI for every team)."""
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
# College offseason: NBA draft pipeline + recruiting (mirrors ui.college_ui._run_offseason)
# ---------------------------------------------------------------------------
def _pipeline_view(world: World) -> dict:
    """Which declared players got drafted into the background NBA, plus the user's own."""
    team = world.user_team
    results = (world.pipeline or {}).get("results", [])

    def row(r: dict) -> dict:
        nba = world.find_team(r["tid"])
        return {"pick": r["pick"], "name": r["name"], "college": r["college"],
                "nba_abbrev": nba.abbrev if nba else "?",
                "nba_color": ser.color_hex(nba.color) if nba else "#9aa0a6"}

    mine = [row(r) for r in results if team is not None and r["college"] == team.full_name]
    return {"drafted": len(results), "mine": mine, "top": [row(r) for r in results[:10]]}


def _recruiting_view(world: World) -> dict:
    """The recruiting board: the open tier of prospects + the user's budget/scholarship state."""
    from hoopsim.gen.collegegen import star_rating
    team = world.user_team
    if world.recruit_wave is not None:
        recruits = recruiting.recruit_wave_pool(world)
    else:
        recruits = sorted(world.recruit_players(), key=lambda p: p.scouted_potential(),
                          reverse=True)
    rows = [{"pid": p.pid, "name": p.name, "position": p.position,
             "secondary_position": p.secondary_position, "stars": star_rating(p),
             "overall": p.overall, "potential": p.scouted_potential()} for p in recruits]
    out: dict = {"economy": world.college_economy, "recruits": rows,
                 "wave": _recruit_wave_view(world)}
    if team is not None:
        if world.college_economy == "nil":
            out["nil_budget"] = team.nil_budget
            out["nil_available"] = collegefin.nil_available(world, team)
        else:
            out["scholarships_open"] = collegefin.scholarships_open(team)
    return out


def _recruit_wave_view(world: World) -> dict:
    """The phased-recruiting banner: which tier is open, or inactive outside Signing Day."""
    if world.recruit_wave is None:
        return {"active": False}
    return {"active": True, "wave": world.recruit_wave + 1,
            "total": recruiting.NUM_RECRUIT_WAVES,
            "name": recruiting.RECRUIT_WAVE_NAMES[world.recruit_wave]}


@app.post("/api/offseason/college/begin")
def college_offseason_begin(sid: str = Depends(_sid)):
    """Develop, run eligibility (declare/return/graduate) + the NBA draft pipeline, and open
    recruiting. Idempotent: re-entering after it's begun this year just resumes (no double-aging)."""
    world = _world(sid)
    if world.mode != "college" or world.phase != Phase.DRAFT:
        raise HTTPException(status_code=409, detail="The college offseason is not active.")
    champ = CT.national_champion(world)
    begun = world.pipeline is not None and world.pipeline.get("year") == world.season_year
    if begun:
        if world.recruit_wave is None:          # resume an in-progress board at the top wave
            recruiting.start_recruiting(world)
        return {"resumed": True, "champion": champ, "pipeline": _pipeline_view(world),
                "recruiting": _recruiting_view(world)}
    summary = CO.pre_recruiting(world, champ)
    recruiting.start_recruiting(world)          # open Signing Day at the five-star wave
    SESSIONS.autosave(sid)
    return {"resumed": False, "summary": summary, "champion": champ,
            "pipeline": _pipeline_view(world), "recruiting": _recruiting_view(world)}


@app.get("/api/recruiting")
def recruiting_board(sid: str = Depends(_sid)):
    world = _world(sid)
    if world.mode != "college":
        raise HTTPException(status_code=409, detail="Recruiting is college-only.")
    return _recruiting_view(world)


@app.post("/api/recruiting/sign")
def recruiting_sign(body: RecruitSignBody, sid: str = Depends(_sid)):
    """Signing Day, one wave at a time: resolve the open tier against AI programs. The top tier
    commits first; missed targets stay on the board. Once the final wave clears, roll into the
    next season."""
    world = _world(sid)
    if world.mode != "college" or world.phase != Phase.DRAFT:
        raise HTTPException(status_code=409, detail="Recruiting is not active.")
    if world.recruit_wave is None:
        recruiting.start_recruiting(world)
    if world.college_economy == "nil":
        offers: Dict[int, object] = {pid: int(amt) for pid, amt in body.offers.items()
                                     if amt and int(amt) > 0}
    else:
        offers = {pid: True for pid in body.offers}
    result = recruiting.resolve_recruiting_wave(world, offers)
    signed = [ser.player_row(world, world.players[pid]) for pid in result["user_signings"]
              if pid in world.players]
    more = recruiting.advance_recruit_wave(world)
    if not more:
        CO.post_recruiting(world)           # fill rosters, season_year += 1, start next season
        SESSIONS.autosave(sid)
        return {"signed": signed, "total": result["total"], "done": True,
                "summary": ser.world_summary(world)}
    SESSIONS.autosave(sid)
    return {"signed": signed, "total": result["total"], "done": False,
            "recruiting": _recruiting_view(world)}


# ---------------------------------------------------------------------------
# Static frontend (built SPA), mounted last so /api/* wins.
# ---------------------------------------------------------------------------
_DIST = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="static")


def run() -> None:
    """Console entry point: serve the app and open a browser."""
    import uvicorn

    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    port = int(os.environ.get("PORT", 8000))
    if os.environ.get("HOOPSIM_NO_BROWSER") != "1" and host == "127.0.0.1":
        try:
            webbrowser.open(f"http://{host}:{port}")
        except Exception:  # noqa: BLE001
            pass
    uvicorn.run("hoopsim.web.app:app", host=host, port=port, reload=False)
