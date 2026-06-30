"""Turn World/Team/Player/GameResult into plain JSON-able dicts for the web API.

This is the web analogue of ``hoopr.ui.widgets``: where the terminal builds ``rich`` tables,
here we emit dicts of the *same computed numbers* and let the browser handle formatting and
sorting. We deliberately reuse the models' computed properties and the existing engine helpers
(``conference_standings``, ``cap`` math, ``team_salary``) rather than recomputing anything.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict, List, Optional

from rich.color import Color

from hoopsim.config import CONFERENCES, ROSTER_MAX, SCHOLARSHIP_LIMIT
from hoopsim.models.attributes import COMPOSITES, POSITIONS, RATING_GROUPS, all_composites
from hoopsim.models.league import Phase, conference_standings
from hoopsim.models.player import Player
from hoopsim.models.team import (
    MAX_ROTATION, ROLE_LABELS, ROLE_TAGS, Team, roster_players, rotation_pool, team_salary,
)
from hoopsim.models.world import World
from hoopsim.sim.boxscore import GameResult
from hoopsim.sim.coach import PRESET_LABELS
from hoopsim.sim.season import game_date, regular_season_complete
from hoopsim.systems import cap
from hoopsim.systems import scouting as SC


# ---------------------------------------------------------------------------
# Colors — resolve rich named colors (e.g. "navy_blue") to CSS hex.
# ---------------------------------------------------------------------------
@lru_cache(maxsize=256)
def color_hex(name: str) -> str:
    try:
        r, g, b = Color.parse(name).get_truecolor()
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:  # noqa: BLE001 - unknown color name; fall back to a neutral
        return "#9aa0a6"


# ---------------------------------------------------------------------------
# Teams & world summary
# ---------------------------------------------------------------------------
def team_brief(team: Team) -> dict:
    """Minimal team identity used for dropdowns, opponent labels, and table cells."""
    return {
        "tid": team.tid,
        "abbrev": team.abbrev,
        "name": team.name,
        "city": team.city,
        "full_name": team.full_name,
        "conference": team.conference,
        "color": color_hex(team.color),
        "league": team.league,
        "prestige": team.prestige,
        "market_size": team.market_size,
    }


def _team_briefs_with_strength(world: World) -> List[dict]:
    """Team identities for selection/dropdowns, tagged with projected strength + a 1–5 star rank."""
    from hoopsim.sim import power
    stars = power.strength_stars(world)
    strength = power.projected_strength(world)
    out = []
    for t in sorted(world.team_list(), key=lambda t: t.full_name):
        b = team_brief(t)
        b["strength"] = strength.get(t.tid)
        b["strength_stars"] = stars.get(t.tid)
        out.append(b)
    return out


def world_conferences(world: World) -> List[str]:
    """Conference names in a stable order (mirrors ui.screens.standings.world_conferences)."""
    if world.mode == "college":
        seen: List[str] = []
        for t in world.team_list():
            if t.conference not in seen:
                seen.append(t.conference)
        return seen
    return list(CONFERENCES)


def _offseason_stage(world: World):
    """Where the resumable offseason wizard is, derived from authoritative world state.

    NBA: ``pre_draft`` (offseason not yet begun) → ``draft`` (class generated, picking) →
    ``free_agency`` (draft done, signing) → ``None`` (season running).
    College: ``pre_recruiting`` (offseason not yet begun) → ``recruiting`` (eligibility + NBA
    pipeline done, signing recruits) → ``None`` (season running).
    """
    if world.mode == "college":
        if world.phase == Phase.DRAFT:
            # pre_recruiting runs the NBA draft pipeline, stamping this year on world.pipeline.
            begun = world.pipeline is not None and world.pipeline.get("year") == world.season_year
            return "recruiting" if begun else "pre_recruiting"
        return None
    if world.phase == Phase.DRAFT:
        return "draft" if world.draft_class is not None else "pre_draft"
    if world.phase == Phase.FREE_AGENCY:
        return "free_agency"
    return None


def world_summary(world: World) -> dict:
    """The status-bar payload (mirrors ui.widgets.header)."""
    team = world.user_team
    out = {
        "season_year": world.season_year,
        "seed": world.rng.seed,
        "phase": world.phase,
        "phase_label": Phase.label(world.phase),
        "offseason_stage": _offseason_stage(world),
        "day": world.day,
        "date": game_date(world, world.day),
        "mode": world.mode,
        "college_economy": world.college_economy,
        "user_team_id": world.user_team_id,
        "salary_cap": world.salary_cap,
        "luxury_tax_line": world.luxury_tax_line,
        "teams": _team_briefs_with_strength(world),
        "conferences": world_conferences(world),
        "regular_season_complete": regular_season_complete(world),
    }
    if team is not None:
        out["user_team"] = team_brief(team)
        out["record"] = team.record_str
        if world.mode == "college":
            from hoopsim.systems import collegefin
            if world.college_economy == "nil":
                out["nil_spent"] = collegefin.nil_spent(world, team)
                out["nil_budget"] = team.nil_budget
            else:
                out["scholarships_used"] = collegefin.scholarships_used(team)
                out["scholarship_limit"] = SCHOLARSHIP_LIMIT
        else:
            out["payroll"] = team_salary(team, world.players)
    if world.mode == "nba":
        from hoopsim.systems import trades
        deadline = trades.trade_deadline_day(world)
        out["trade_deadline_day"] = deadline
        out["trade_deadline_passed"] = trades.trade_deadline_passed(world)
        out["days_to_deadline"] = max(0, deadline - world.day)
        out["open_offers"] = len(world.trade_offers)
    return out


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------
def off_def_ratings(ratings: Dict[str, int]) -> Dict[str, int]:
    """Two at-a-glance summary numbers: offense (scoring+playmaking) and defense."""
    comps = all_composites(ratings)
    return {
        "off": round(0.6 * comps["scoring"] + 0.4 * comps["playmaking"]),
        "def": round(comps["defense"]),
    }


def player_row(world: World, p: Player, *, is_starter: bool = False) -> dict:
    """A roster/list row (mirrors ui.widgets.roster_table). Raw numbers; UI formats them."""
    s = p.season
    team = world.find_team(p.team_id) if p.team_id is not None else None
    pv = SC.pot_view(p)
    return {
        "pid": p.pid,
        "jersey": p.jersey,
        "name": p.name,
        "short_name": p.short_name,
        "position": p.position,
        "secondary_position": p.secondary_position,
        "archetype": p.archetype,
        "age": p.age,
        "class_year": p.class_year,
        "overall": p.overall,
        "potential": p.scouted_potential(),
        # Fogged potential for display: grade is always safe; band collapses once known.
        "pot_grade": pv.grade,
        "pot_low": pv.low,
        "pot_high": pv.high,
        "pot_known": pv.known,
        "ppg": round(s.ppg, 1),
        "rpg": round(s.rpg, 1),
        "apg": round(s.apg, 1),
        "gp": s.gp,
        "salary": p.contract.current_salary,
        "years_remaining": p.contract.years_remaining,
        "is_starter": is_starter,
        "is_injured": p.is_injured,
        "injury": (p.injury.description if p.is_injured else None),
        "injury_games": (p.injury.games_remaining if p.is_injured else 0),
        "team_id": p.team_id,
        "team_abbrev": (team.abbrev if team else "FA"),
        "team_color": (color_hex(team.color) if team else "#9aa0a6"),
        "on_block": bool(team is not None and p.pid in team.block_list),
        "dead_money_if_waived": (sum(World.dead_money_schedule(p.contract)) if team else 0),
    }


def prospect_row(world: World, p: Player) -> dict:
    """A draft-board row: identity, fogged potential, archetype, and the pre-draft stat line."""
    row = player_row(world, p)
    keep = ("pid", "name", "position", "secondary_position", "age", "overall", "potential",
            "pot_grade", "pot_low", "pot_high", "pot_known", "archetype")
    out = {k: row[k] for k in keep}
    out["pre_draft"] = dict(p.pre_draft) if p.pre_draft else None
    return out


def scouting_row(world: World, p: Player, *, on_block: bool = False) -> dict:
    """A league-scouting row: the roster row plus composite ratings and a trade-block flag."""
    row = player_row(world, p)
    row["composites"] = {name: round(v) for name, v in all_composites(p.ratings).items()}
    row["on_block"] = on_block
    return row


def scouting_view(world: World, *, include_fa: bool = True) -> dict:
    """Every player in the league with attributes — the scouting board for trades/targets."""
    from hoopsim.systems import trades
    rows: List[dict] = []
    for team in world.team_list():
        block = (set() if team.tid == world.user_team_id
                 else set(trades.team_trade_block(world, team)))
        for p in roster_players(team, world.players):
            rows.append(scouting_row(world, p, on_block=p.pid in block))
    if include_fa:
        for p in world.free_agent_players():
            rows.append(scouting_row(world, p))
    return {"players": rows, "composite_order": list(COMPOSITES)}


def depth_chart_view(world: World, team: Team) -> dict:
    """Roster grouped by position (starters first, then by overall) — where you're deep or thin."""
    starters = set(team.starters)
    groups = []
    for pos in POSITIONS:
        players = [p for p in roster_players(team, world.players) if p.position == pos]
        players.sort(key=lambda p: (p.pid in starters, p.overall), reverse=True)
        groups.append({
            "position": pos,
            "count": len(players),
            "players": [player_row(world, p, is_starter=p.pid in starters) for p in players],
        })
    return {"team": team_brief(team), "positions": groups, "roster_max": ROSTER_MAX}


def _enrich_award(world: World, e) -> dict:
    """Add a display color to a stored award entry from its (live) team id."""
    if not isinstance(e, dict):
        return e
    team = world.find_team(e.get("tid")) if e.get("tid") is not None else None
    out = dict(e)
    out["team_color"] = color_hex(team.color) if team else "#9aa0a6"
    return out


def history_view(world: World) -> List[dict]:
    """Past seasons (most recent first): champion plus award winners, ready for display."""
    out: List[dict] = []
    for entry in reversed(world.history):
        champ = world.find_team(entry.get("champion")) if entry.get("champion") is not None else None
        awards = entry.get("awards") or {}
        enriched: dict = {}
        for key in ("mvp", "roy", "dpoy", "mip"):
            if key in awards:
                enriched[key] = _enrich_award(world, awards[key])
        if "all_league" in awards:
            enriched["all_league"] = [[_enrich_award(world, p) for p in team_]
                                      for team_ in awards["all_league"]]
        if "leaders" in awards:
            enriched["leaders"] = {k: _enrich_award(world, v) for k, v in awards["leaders"].items()}
        out.append({
            "year": entry.get("year"),
            "champion": entry.get("champion"),
            "champion_name": entry.get("champion_name", ""),
            "champion_abbrev": champ.abbrev if champ else "",
            "champion_color": color_hex(champ.color) if champ else "#9aa0a6",
            "awards": enriched,
        })
    return out


def roster_view(world: World, team: Team) -> dict:
    starters = set(team.starters)
    # Effective rotation (beyond the starters) — who actually draws minutes, manual or automatic.
    rotation = [p.pid for p in rotation_pool(team, world.players) if p.pid not in starters]
    players = sorted(roster_players(team, world.players), key=lambda p: p.overall, reverse=True)
    rows = []
    for p in players:
        row = player_row(world, p, is_starter=p.pid in starters)
        row.update(off_def_ratings(p.ratings))                  # off/def at-a-glance (lineup page)
        row["minutes"] = team.minutes_target.get(p.pid, 0)      # projected rotation minutes
        rows.append(row)
    return {
        "team": team_brief(team),
        "players": rows,
        "roster_max": ROSTER_MAX,
        "starters": list(team.starters),
        "auto_lineup": team.auto_lineup,
        "rotation": rotation,
        "manual_rotation": bool(team.rotation),
        "max_rotation": MAX_ROTATION,
        "roles": {role: team.roles[role] for role in ROLE_TAGS if role in team.roles},
        "role_tags": list(ROLE_TAGS),
        "role_labels": dict(ROLE_LABELS),
    }


def player_detail(world: World, p: Player) -> dict:
    """Full ratings card (mirrors ui.widgets.player_card) plus season/career stats."""
    groups = {
        group: [{"key": k, "label": k.replace("_", " ").title(), "value": p.ratings[k]}
                for k in keys]
        for group, keys in RATING_GROUPS.items()
        if group != "Marketability" or world.mode == "college"
    }
    composites = {name: round(v, 1) for name, v in all_composites(p.ratings).items()}
    s = p.season
    base = player_row(world, p)
    base.update({
        "height": p.height_str,
        "weight_lb": p.weight_lb,
        "experience": p.experience,
        "college": p.college,
        "draft": dict(p.draft) if p.draft else None,
        "morale": p.morale,
        "rating_groups": groups,
        "composites": composites,
        "composite_order": list(COMPOSITES),
        "season_stats": {
            "gp": s.gp, "gs": s.gs, "mpg": round(s.mpg, 1), "ppg": round(s.ppg, 1),
            "rpg": round(s.rpg, 1), "apg": round(s.apg, 1),
            "spg": round(s.per_game("stl"), 1), "bpg": round(s.per_game("blk"), 1),
            "topg": round(s.per_game("tov"), 1),
            "fg_pct": round(s.fg_pct, 3), "tp_pct": round(s.tp_pct, 3),
            "ft_pct": round(s.ft_pct, 3), "ts_pct": round(s.ts_pct, 3),
        },
        "career": list(p.career),
        "legacy": legacy_resume_view(world, p),
    })
    return base


def legacy_resume_view(world: World, p: Player) -> dict:
    """Career résumé for the legacy/career page: totals, peak, accolades, and HoF standing."""
    from hoopsim.systems import legacy
    r = legacy.resume(world, p)
    return {
        "seasons": r["seasons"],
        "peak_ovr": r["peak_ovr"],
        "totals": r["totals"],
        "accolades": [{"key": k, "label": legacy.ACCOLADE_LABELS.get(k, k), "count": v}
                      for k, v in sorted(r["accolades"].items(),
                                         key=lambda kv: -legacy.ACCOLADE_WEIGHTS.get(kv[0], 0))],
        "hof_score": r["hof_score"],
        "hof": r["hof"],
    }


def hall_of_fame_view(world: World) -> List[dict]:
    """Inducted greats, highest HoF score first — self-contained résumé snapshots."""
    from hoopsim.systems import legacy
    rows = sorted(world.hall_of_fame, key=lambda s: s.get("hof_score", 0), reverse=True)
    return [_resume_row(world, s, legacy) for s in rows]


def leaderboards_view(world: World, category: str = "pts", limit: int = 25) -> dict:
    """All-time career leaders (living + retired) for the record book."""
    from hoopsim.systems import legacy
    rows = legacy.leaderboards(world, category, limit)
    return {
        "category": category,
        "categories": list(legacy.LEADERBOARD_CATEGORIES),
        "rows": [_resume_row(world, s, legacy) for s in rows],
    }


def _resume_row(world: World, snap: dict, legacy) -> dict:
    """Flatten a résumé snapshot into a display row (used by HoF + leaderboards)."""
    return {
        "pid": snap.get("pid"),
        "name": snap.get("name"),
        "position": snap.get("position"),
        "seasons": snap.get("seasons"),
        "peak_ovr": snap.get("peak_ovr"),
        "last_team": snap.get("last_team"),
        "first_year": snap.get("first_year"),
        "last_year": snap.get("last_year"),
        "draft": snap.get("draft"),
        "active": snap.get("active", snap.get("pid") in world.players),
        "totals": snap.get("totals", {}),
        "accolades": [{"key": k, "label": legacy.ACCOLADE_LABELS.get(k, k), "count": v}
                      for k, v in snap.get("accolades", {}).items() if v],
        "hof_score": snap.get("hof_score"),
        "hof": snap.get("hof", False),
        "induction_year": snap.get("induction_year"),
    }


# ---------------------------------------------------------------------------
# Standings & leaders
# ---------------------------------------------------------------------------
def standings_view(world: World) -> dict:
    """Conference standings with GB and seed markers (mirrors ui.widgets.standings_table)."""
    from hoopsim.sim import power
    pwr = power.power_map(world)
    confs = []
    for conf in world_conferences(world):
        teams = conference_standings(world.team_list(), conf)
        leader_w = teams[0].wins if teams else 0
        leader_l = teams[0].losses if teams else 0
        rows = []
        for i, t in enumerate(teams, start=1):
            gb = ((leader_w - t.wins) + (t.losses - leader_l)) / 2
            pr = pwr.get(t.tid)
            rows.append({
                "rank": i,
                "tid": t.tid,
                "abbrev": t.abbrev,
                "name": t.name,
                "color": color_hex(t.color),
                "wins": t.wins,
                "losses": t.losses,
                "win_pct": round(t.win_pct, 3),
                "gb": round(gb, 1),
                "streak": t.streak_str,
                "point_diff": t.point_diff,
                "power": round(pr.power, 1) if pr else 0.0,       # net rating
                "power_rank": pr.rank if pr else 0,               # 1..N leaguewide
                "is_user": t.tid == world.user_team_id,
            })
        confs.append({"conference": conf, "teams": rows})
    return {"mode": world.mode, "conferences": confs}


def power_view(world: World) -> dict:
    """League power ratings (BPI/SRS-style net rating), best-first, for the Power tab."""
    from hoopsim.sim import power
    teams = {t.tid: t for t in world.team_list()}
    rows = []
    for r in power.power_ratings(world):
        t = teams[r.tid]
        rows.append({
            "rank": r.rank,
            "tid": r.tid,
            "abbrev": t.abbrev,
            "name": t.full_name,
            "color": color_hex(t.color),
            "conference": t.conference,
            "record": t.record_str,
            "win_pct": round(t.win_pct, 3),
            "power": round(r.power, 1),
            "srs": round(r.srs, 1),
            "prior": round(r.prior, 1),
            "sos": round(r.sos, 1),
            "proj_win_pct": round(r.proj_win_pct, 3),
            "is_user": t.tid == world.user_team_id,
        })
    return {"teams": rows, "games_played": max((t.games_played for t in world.team_list()),
                                               default=0)}


_LEADER_STATS = [
    ("ppg", "PPG"), ("rpg", "RPG"), ("apg", "APG"),
    ("spg", "SPG"), ("bpg", "BPG"),
]


def leaders_view(world: World, *, top: int = 10) -> dict:
    """League leaders across several categories (generalizes ui.app_ui._league_leaders)."""
    threshold = max(1, world.day // 4)
    qualified = [p for p in world.players.values() if p.season.gp >= threshold]

    def value(p: Player, stat: str) -> float:
        s = p.season
        if stat == "spg":
            return s.per_game("stl")
        if stat == "bpg":
            return s.per_game("blk")
        return getattr(s, stat)

    cats = []
    for stat, label in _LEADER_STATS:
        ranked = sorted(qualified, key=lambda p: value(p, stat), reverse=True)[:top]
        cats.append({
            "stat": stat,
            "label": label,
            "leaders": [{
                "pid": p.pid,
                "name": p.name,
                "team_abbrev": (world.find_team(p.team_id).abbrev if p.team_id is not None
                                and world.find_team(p.team_id) else "FA"),
                "value": round(value(p, stat), 1),
            } for p in ranked],
        })
    return {"categories": cats}


# ---------------------------------------------------------------------------
# Finances (mirrors ui.screens.finances; reuses systems.cap)
# ---------------------------------------------------------------------------
def finances_view(world: World, team: Team) -> dict:
    rows = []
    players = sorted(roster_players(team, world.players),
                     key=lambda p: p.contract.current_salary, reverse=True)
    for p in players:
        market = cap.market_salary(p)
        rows.append({
            "pid": p.pid,
            "name": p.name,
            "position": p.position,
            "age": p.age,
            "overall": p.overall,
            "salary": p.contract.current_salary,
            "years_remaining": p.contract.years_remaining,
            "market_value": market,
            "surplus": market - p.contract.current_salary,
            "dead_money_if_waived": sum(World.dead_money_schedule(p.contract)),
        })
    return {
        "team": team_brief(team),
        "payroll": cap.payroll(world, team),
        "salary_cap": world.salary_cap,
        "cap_space": cap.cap_space(world, team),
        "luxury_tax_line": world.luxury_tax_line,
        "luxury_tax": cap.luxury_tax(world, team),
        "owner_budget": team.owner_budget,
        "dead_money": (team.dead_money[0] if team.dead_money else 0),
        "dead_money_future": sum(team.dead_money[1:]) if len(team.dead_money) > 1 else 0,
        "contracts": rows,
    }


# ---------------------------------------------------------------------------
# Draft picks & solicited trade offers
# ---------------------------------------------------------------------------
def pick_view(world: World, pick) -> dict:
    """A tradeable draft pick: its key, a human label, and asset value."""
    orig = world.find_team(pick.original_tid)
    owner = world.find_team(pick.owner_tid)
    rnd = {1: "1st", 2: "2nd"}.get(pick.round, f"R{pick.round}")
    label = f"{pick.year} {rnd}"
    if orig is not None and pick.original_tid != pick.owner_tid:
        label += f" (via {orig.abbrev})"      # acquired from another team
    return {
        "key": [pick.year, pick.round, pick.original_tid],
        "year": pick.year,
        "round": pick.round,
        "original_tid": pick.original_tid,
        "original_abbrev": orig.abbrev if orig else "?",
        "owner_tid": pick.owner_tid,
        "owner_abbrev": owner.abbrev if owner else "?",
        "label": label,
        "value": cap.pick_value(world, pick),
    }


def offer_view(world: World, o: dict) -> dict:
    """Serialize a stored AI-initiated offer for the user's inbox."""
    frm = world.find_team(o["from_tid"])

    def _piece(pid: int) -> dict:
        p = world.players[pid]
        return {"pid": pid, "name": p.name, "position": p.position, "age": p.age,
                "overall": p.overall, "salary": p.contract.current_salary}

    picks = [world.find_pick(*k) for k in o.get("team_picks", [])]
    return {
        "id": o["id"],
        "from_tid": o["from_tid"],
        "from_abbrev": frm.abbrev if frm else "?",
        "from_name": frm.full_name if frm else "?",
        "from_color": color_hex(frm.color) if frm else "#9aa0a6",
        "user_sends": list(o["user_sends"]),
        "team_sends": list(o["team_sends"]),
        "team_picks": [list(k) for k in o.get("team_picks", [])],
        "wants": [_piece(pid) for pid in o["user_sends"]],     # your players they're after
        "gives": [_piece(pid) for pid in o["team_sends"]],     # what comes back
        "picks": [pick_view(world, p) for p in picks if p is not None],
        "value": o["value"],
        "unsolicited": o.get("unsolicited", False),
        "expires_in": max(0, o["expires_day"] - world.day),
    }


def solicited_offer_view(world: World, so) -> dict:
    """Serialize a ``trades.SolicitedOffer`` for the "shop my player" panel."""
    offer = so.offer
    partner = world.find_team(offer.b)

    def _piece(pid: int) -> dict:
        p = world.players[pid]
        return {"pid": pid, "name": p.name, "position": p.position, "age": p.age,
                "overall": p.overall, "salary": p.contract.current_salary,
                "value": round(cap.trade_value(p), 1)}

    pick_objs = [world.find_pick(*k) for k in offer.b_picks]
    user_pick_objs = [world.find_pick(*k) for k in offer.a_picks]
    return {
        "partner_tid": offer.b,
        "partner_abbrev": partner.abbrev,
        "partner_name": partner.full_name,
        "partner_color": color_hex(partner.color),
        "user_sends": offer.a_sends,
        "user_picks": [list(k) for k in offer.a_picks],       # picks the user gives up
        "partner_sends": offer.b_sends,
        "partner_picks": [list(k) for k in offer.b_picks],
        "pieces": [_piece(pid) for pid in offer.b_sends],
        "picks": [pick_view(world, p) for p in pick_objs if p is not None],
        "gives_picks": [pick_view(world, p) for p in user_pick_objs if p is not None],
        "value": round(so.value, 1),
        "target_value": round(so.target_value, 1),
    }


# ---------------------------------------------------------------------------
# Free agents
# ---------------------------------------------------------------------------
def free_agents_view(world: World) -> dict:
    from hoopsim.systems import freeagency
    team = world.user_team
    if world.fa_wave is not None:
        fas = freeagency.fa_wave_pool(world)            # only the open tier, cooled pricing
    else:
        fas = sorted(world.free_agent_players(), key=lambda p: p.overall, reverse=True)
    from hoopsim.config import MAX_CONTRACT_YEARS
    rows = []
    for p in fas:
        ask = freeagency.wave_market_salary(world, p)
        can_sign, reason = (cap.can_sign(world, team, ask) if team else (False, ""))
        row = player_row(world, p)
        row["ask"] = ask
        row["can_sign"] = can_sign
        row["sign_reason"] = reason
        row["preferred_years"] = freeagency.contract_years_for(p)
        # Salary the player requires at each contract length — lets the offer UI trade term vs money.
        row["required_by_years"] = {str(y): freeagency.required_salary(world, p, y)
                                    for y in range(1, MAX_CONTRACT_YEARS + 1)}
        rows.append(row)
    return {"free_agents": rows, "wave": fa_wave_view(world), "max_years": MAX_CONTRACT_YEARS}


def fa_wave_view(world: World) -> dict:
    """The tiered free-agency banner: which wave is open, or inactive outside the offseason."""
    from hoopsim.systems import freeagency
    if world.fa_wave is None:
        return {"active": False}
    return {
        "active": True,
        "wave": world.fa_wave + 1,
        "total": freeagency.NUM_FA_WAVES,
        "name": freeagency.FA_WAVE_NAMES[world.fa_wave],
    }


# ---------------------------------------------------------------------------
# Game results (box score, line score, play-by-play)
# ---------------------------------------------------------------------------
def _box_rows(world: World, result: GameResult, tid: int) -> List[dict]:
    team = world.find_team(tid)
    lines = [(pid, result.box[pid]) for pid in team.roster if pid in result.box]
    lines.sort(key=lambda kv: kv[1].secs, reverse=True)
    rows = []
    for pid, s in lines:
        if s.secs == 0:
            continue
        p = world.players[pid]
        rows.append({
            "pid": pid, "name": p.short_name, "min": round(s.minutes),
            "pts": s.pts, "reb": s.reb, "ast": s.ast, "stl": s.stl, "blk": s.blk,
            "tov": s.tov, "fgm": s.fgm, "fga": s.fga, "tpm": s.tpm, "tpa": s.tpa,
            "ftm": s.ftm, "fta": s.fta, "plus_minus": s.plus_minus,
        })
    return rows


def game_result_view(world: World, result: GameResult) -> dict:
    home = world.find_team(result.home_tid)
    away = world.find_team(result.away_tid)
    return {
        "home": team_brief(home),
        "away": team_brief(away),
        "home_score": result.home_score,
        "away_score": result.away_score,
        "period_label": result.period_label,
        "line_score": [{"home": ls[0], "away": ls[1]} for ls in result.line_score],
        "box": {
            "home": _box_rows(world, result, result.home_tid),
            "away": _box_rows(world, result, result.away_tid),
        },
        "pbp": [{
            "quarter": e.quarter, "clock": e.clock,
            "tid": e.tid, "text": e.text,
            "home_score": e.home_score, "away_score": e.away_score,
        } for e in result.pbp],
    }


def _clock_str(secs) -> str:
    secs = max(0, int(secs))
    m, s = divmod(secs, 60)
    return f"{m}:{s:02d}"


def coach_event_view(world: World, e) -> dict:
    """One crunch-time play-by-play line, with the acting team's identity for coloring."""
    team = world.find_team(e.tid) if e.tid is not None else None
    return {
        "quarter": e.quarter, "clock": e.clock, "text": e.text,
        "home_score": e.home_score, "away_score": e.away_score,
        "tid": e.tid,
        "abbrev": team.abbrev if team else None,
        "color": color_hex(team.color) if team else None,
    }


def coach_view_json(world: World, view) -> dict:
    """Serialize a :class:`~hoopr.sim.coach.CoachView` for the browser crunch-time panel."""
    def pj(p) -> dict:
        row = {"pid": p.pid, "name": p.name, "pos": p.pos, "overall": p.overall,
               "fouls": p.fouls, "fatigue": round(p.fatigue, 1), "secs": int(p.secs),
               "fouled_out": p.fouled_out}
        player = world.players.get(p.pid)
        if player is not None:                       # off/def + key skills to inform subs
            r = player.ratings
            row.update(off_def_ratings(r))
            row["skills"] = {"finishing": r["finishing"], "three": r["three_point"],
                             "perimeter_def": r["perimeter_def"],
                             "interior_def": r["interior_def"], "iq": r["basketball_iq"]}
        return row

    user = world.teams[world.user_team_id]
    return {
        "quarter": view.quarter, "periods": view.periods,
        "clock": int(view.clock), "clock_str": _clock_str(view.clock),
        "period_label": view.period_label,
        "home_abbrev": view.home_abbrev, "away_abbrev": view.away_abbrev,
        "home_score": view.home_score, "away_score": view.away_score,
        "user_is_home": view.user_is_home, "user_on_offense": view.user_on_offense,
        "user_score": view.user_score, "opp_score": view.opp_score, "user_lead": view.user_lead,
        "user_timeouts": view.user_timeouts, "opp_timeouts": view.opp_timeouts,
        "user_in_bonus": view.user_in_bonus, "opp_in_bonus": view.opp_in_bonus,
        "on_court": [pj(p) for p in view.on_court],
        "bench": [pj(p) for p in view.bench],
        "user_team": team_brief(user),
        "first_engagement": view.first_engagement,
        "sub_only": view.sub_only,
        "hint": view.hint,
        # Situational one-tap fives: [{key, label, blurb, lineup:[pid,...]}, ...] in display order.
        "presets": [
            {"key": key, "label": label, "blurb": blurb, "lineup": view.presets[key]}
            for key, label, blurb in PRESET_LABELS if key in view.presets
        ],
    }


def schedule_result(world: World, game) -> dict:
    """A one-line played-game summary (for recent-results lists)."""
    home, away = world.find_team(game.home), world.find_team(game.away)
    return {
        "gid": game.gid, "day": game.day,
        "home": team_brief(home), "away": team_brief(away),
        "home_score": game.home_score, "away_score": game.away_score,
        "played": game.played, "is_playoff": game.is_playoff,
        "winner": game.winner,
    }
