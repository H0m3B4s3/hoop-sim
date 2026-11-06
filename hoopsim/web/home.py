"""The Home screen: what needs the user's attention, and where the season stands.

Presentation only, like ``serializers.py``: every number comes from the engine. Inbox items carry
the tab that resolves them so the browser can link straight there.
"""
from __future__ import annotations

from typing import List

from hoopsim.config import ROSTER_MAX, ROSTER_MIN
from hoopsim.models.league import Phase, conference_standings
from hoopsim.models.team import roster_players
from hoopsim.models.world import World
from hoopsim.web.serializers import news_view, schedule_result, team_brief

RECENT_GAMES = 5
TEAM_NEWS = 5
INJURY_GAMES = 5            # absences shorter than this aren't worth an inbox line
DEADLINE_WARNING_DAYS = 7
ROTATION = 8                # the players whose contracts and health the user cares about most

# Inbox severity, highest first.
URGENT, ACTION, INFO = "urgent", "action", "info"
_ORDER = {URGENT: 0, ACTION: 1, INFO: 2}


def _item(severity: str, text: str, tab: str) -> dict:
    return {"severity": severity, "text": text, "tab": tab}


def _inbox(world: World, team) -> List[dict]:
    from hoopsim.systems import cap, contract_mood, owner, trades
    items: List[dict] = []
    nba = world.mode == "nba"
    rotation = sorted(roster_players(team, world.players), key=lambda p: p.overall,
                      reverse=True)[:ROTATION]

    if nba and world.trade_offers:
        soon = min(o["expires_day"] for o in world.trade_offers) - world.day
        n = len(world.trade_offers)
        items.append(_item(ACTION, f"{n} trade offer{'s' if n != 1 else ''} waiting"
                           f" (next expires in {max(0, soon)} day{'s' if soon != 1 else ''})",
                           "offers"))
    if nba and world.phase == Phase.REGULAR_SEASON and not trades.trade_deadline_passed(world):
        left = trades.trade_deadline_day(world) - world.day
        if left <= DEADLINE_WARNING_DAYS:
            items.append(_item(ACTION if left > 2 else URGENT,
                               "Trade deadline is today" if left == 0
                               else f"Trade deadline in {left} day{'s' if left != 1 else ''}",
                               "trade"))
    for p in rotation:
        if p.injury is not None and p.injury.games_remaining >= INJURY_GAMES:
            items.append(_item(INFO, f"{p.name} is out about {p.injury.games_remaining} games "
                                     f"({p.injury.description})", "injuries"))
    if len(team.roster) < ROSTER_MIN:
        items.append(_item(URGENT, f"Roster is below the minimum ({len(team.roster)} of "
                                   f"{ROSTER_MIN}): sign a free agent", "fa"))
    elif len(team.roster) > ROSTER_MAX:
        items.append(_item(URGENT, f"Roster is over the maximum ({len(team.roster)} of "
                                   f"{ROSTER_MAX}): waive or trade someone", "roster"))
    if nba:
        for p in rotation:
            if p.contract.years_remaining != 1:
                continue
            mood = contract_mood.assess(world, p)
            if mood["level"] == contract_mood.TESTING_FA:
                items.append(_item(ACTION, f"{p.name}'s contract expires this season, and he "
                                           f"plans to test free agency", "finances"))
            elif mood["level"] in (contract_mood.EAGER, contract_mood.OPEN):
                items.append(_item(INFO, f"{p.name}'s contract expires this season; he is "
                                         f"{mood['label'].lower()}", "finances"))
        tax = cap.luxury_tax(world, team)
        if tax > 0:
            items.append(_item(INFO, f"You're over the tax line: ${tax / 1_000_000:.1f}M in "
                                     f"luxury tax", "finances"))
        state = owner.view(world)
        if state and not state["honeymoon"] and state["confidence"] < 45:
            items.append(_item(URGENT if state["confidence"] < owner.FIRE_BELOW + 5 else ACTION,
                               f"Owner confidence is {state['confidence']} "
                               f"({state['standing'].lower()})", "play"))
    items.sort(key=lambda i: _ORDER[i["severity"]])
    return items


def _standing(world: World, team) -> dict:
    order = conference_standings(world.team_list(), team.conference)
    rank = order.index(team) + 1
    leader = order[0]
    back = ((leader.wins - team.wins) + (team.losses - leader.losses)) / 2
    out = {"conference": team.conference, "rank": rank, "of": len(order),
           "record": team.record_str, "games_back": back, "streak": team.streak}
    if team.games_played:
        from hoopsim.sim import power
        out["power_rank"] = next(r.rank for r in power.power_ratings(world) if r.tid == team.tid)
    return out


def home_view(world: World) -> dict:
    from hoopsim.sim import season as S
    from hoopsim.systems import news
    team = world.user_team
    if team is None:
        return {"inbox": [], "news": []}
    nxt = S.user_next_game(world) if world.phase == Phase.REGULAR_SEASON else None
    played = sorted((g for g in world.schedule if g.played and g.involves(team.tid)),
                    key=lambda g: g.day)[-RECENT_GAMES:]
    leaders = sorted((p for p in roster_players(team, world.players) if p.season.gp),
                     key=lambda p: p.season.ppg, reverse=True)[:3]
    out = {
        "inbox": _inbox(world, team),
        "standing": _standing(world, team),
        "recent": [schedule_result(world, g) for g in reversed(played)],
        "leaders": [{"pid": p.pid, "name": p.name, "position": p.position,
                     "ppg": round(p.season.ppg, 1), "rpg": round(p.season.rpg, 1),
                     "apg": round(p.season.apg, 1)} for p in leaders],
        "news": news_view(world, news.recent(world, tid=team.tid, limit=TEAM_NEWS))["items"],
    }
    if nxt is not None:
        opp = world.teams[nxt.opponent_of(team.tid)]
        out["next_game"] = {"day": nxt.day, "date": S.game_date(world, nxt.day),
                            "home": nxt.home == team.tid, "opponent": team_brief(opp),
                            "opponent_record": opp.record_str}
    return out
