"""Writing to the league news wire.

Every system that produces something worth reading calls :func:`emit` (or one of the typed
helpers below) at the moment it happens. This module is deliberately the only writer, so the
save-size cap and the phrasing conventions live in exactly one place.

Two rules the callers depend on:

* **Emitting must never be able to break the sim.** A news call sits inside trade execution,
  injury application and the offseason; a bad format string or a missing player should not take
  a season down with it. :func:`emit` is total — it clamps unknown categories and tolerates
  missing names rather than raising.
* **Headlines are frozen at write time.** Never store a pid and render the name later; the
  player may be traded, retired, or gone from ``world.players`` by the time anyone reads it.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from hoopsim.models.news import CATEGORIES, MAJOR, MINOR, NORMAL, NewsItem
from hoopsim.models.world import World

# Saves carry the wire, so it is a ring buffer rather than an unbounded log. 600 items is roughly
# a season and a half of feed at observed emission rates — enough to scroll back through last
# year's storylines, small enough to stay inconsequential next to the roster data in a save.
MAX_ITEMS = 600

# Statistical thresholds for automatic game recaps. Set high enough that a recap means something:
# a 40-point night should be an event, not a nightly occurrence.
BIG_SCORING_GAME = 40
HUGE_SCORING_GAME = 55
TRIPLE_DOUBLE_MIN = 10
HOT_STREAK = 8            # consecutive wins before it is a story
COLD_STREAK = -8


def emit(world: World, category: str, headline: str, *, importance: int = NORMAL,
         tids: Optional[Sequence[int]] = None, pids: Optional[Sequence[int]] = None,
         detail: str = "") -> Optional[NewsItem]:
    """Append one item to the wire. Total by design — never raises into a caller."""
    if not headline:
        return None
    item = NewsItem(
        year=getattr(world, "season_year", 0),
        day=getattr(world, "day", 0),
        category=category if category in CATEGORIES else "game",
        headline=headline,
        importance=importance,
        tids=list(tids or []),
        pids=list(pids or []),
        detail=detail,
    )
    world.news.append(item)
    if len(world.news) > MAX_ITEMS:
        del world.news[:len(world.news) - MAX_ITEMS]
    return item


def _team_name(world: World, tid) -> str:
    team = world.teams.get(tid) if tid is not None else None
    return team.full_name if team is not None else "A team"


def recent(world: World, *, category: Optional[str] = None, tid: Optional[int] = None,
           min_importance: int = MINOR, limit: int = 60) -> List[NewsItem]:
    """Most recent items first, optionally filtered. This is what the feed reads."""
    items = [n for n in world.news if n.importance >= min_importance]
    if category:
        items = [n for n in items if n.category == category]
    if tid is not None:
        items = [n for n in items if tid in n.tids]
    return list(reversed(items))[:limit]


# ---------------------------------------------------------------------------
# Typed emitters — one per storyline the engine already computes
# ---------------------------------------------------------------------------
# Minimum overall for an injury of each severity to be worth reporting. Without this the wire is
# 80% bench players tweaking an ankle: a full season emitted 463 injury items against 137 of
# everything else, and the genuine stories got evicted by the ring buffer before anyone read them.
_INJURY_NEWSWORTHY = {"minor": 76, "moderate": 68, "major": 0}


def injury(world: World, player, inj) -> None:
    if player.overall < _INJURY_NEWSWORTHY.get(inj.severity, 0):
        return
    sev = {"minor": MINOR, "moderate": NORMAL, "major": MAJOR}.get(inj.severity, NORMAL)
    weeks = max(1, round(inj.games_remaining / 3.5))
    detail = (f"Expected out roughly {weeks} week{'s' if weeks != 1 else ''} "
              f"({inj.games_remaining} games).")
    verb = "will miss extended time with" if inj.severity == "major" else "is out with"
    emit(world, "injury", f"{player.name} {verb} a {inj.description}",
         importance=sev, tids=[player.team_id], pids=[player.pid], detail=detail)


def returned(world: World, player) -> None:
    # A return is less of a story than the injury was, so it clears a higher bar than the
    # moderate-injury threshold that let it be reported in the first place.
    if player.overall < _INJURY_NEWSWORTHY["minor"]:
        return
    emit(world, "injury", f"{player.name} is back in the lineup",
         importance=MINOR, tids=[player.team_id], pids=[player.pid])


def big_game(world: World, player, line) -> None:
    """A standout individual performance. Called once per player per game, so it must be cheap."""
    pts, reb, ast = line.pts, line.reb, line.ast
    doubles = sum(1 for v in (pts, reb, ast) if v >= TRIPLE_DOUBLE_MIN)
    if pts >= HUGE_SCORING_GAME:
        emit(world, "game", f"{player.name} erupts for {pts}",
             importance=MAJOR, tids=[player.team_id], pids=[player.pid],
             detail=f"{pts} pts, {reb} reb, {ast} ast.")
    elif doubles >= 3:
        emit(world, "game", f"{player.name} posts a triple-double",
             importance=NORMAL, tids=[player.team_id], pids=[player.pid],
             detail=f"{pts} pts, {reb} reb, {ast} ast.")
    elif pts >= BIG_SCORING_GAME:
        emit(world, "game", f"{player.name} drops {pts}",
             importance=NORMAL, tids=[player.team_id], pids=[player.pid],
             detail=f"{pts} pts, {reb} reb, {ast} ast.")


def streak(world: World, team) -> None:
    if team.streak == HOT_STREAK:
        emit(world, "game", f"{team.full_name} have won {team.streak} straight",
             importance=NORMAL, tids=[team.tid])
    elif team.streak == COLD_STREAK:
        emit(world, "game", f"{team.full_name} have dropped {abs(team.streak)} in a row",
             importance=NORMAL, tids=[team.tid])


def trade(world: World, a, b, a_out: Sequence, b_out: Sequence,
          a_picks: int = 0, b_picks: int = 0) -> None:
    def side(players, picks):
        names = ", ".join(p.name for p in players) or "cash"
        if picks:
            names += f" and {picks} pick{'s' if picks != 1 else ''}"
        return names
    headline = f"{a.full_name} trade {side(a_out, a_picks)} to {b.abbrev}"
    detail = f"{b.full_name} send {side(b_out, b_picks)} the other way."
    star = max([p.overall for p in list(a_out) + list(b_out)] or [0])
    emit(world, "transaction", headline,
         importance=MAJOR if star >= 82 else NORMAL,
         tids=[a.tid, b.tid], pids=[p.pid for p in list(a_out) + list(b_out)], detail=detail)


def signing(world: World, player, team, salary: int, years: int) -> None:
    emit(world, "transaction",
         f"{team.full_name} sign {player.name}",
         importance=MAJOR if player.overall >= 82 else NORMAL,
         tids=[team.tid], pids=[player.pid],
         detail=f"${salary:,} per year over {years} year{'s' if years != 1 else ''}.")


def waived(world: World, player, team) -> None:
    emit(world, "transaction", f"{team.full_name} waive {player.name}",
         importance=MINOR, tids=[team.tid], pids=[player.pid])


def drafted(world: World, player, team, rnd: int, pick: int) -> None:
    # First round only. Reporting all 60 selections buries a day's feed under second-round picks
    # nobody follows, which is roughly how real draft coverage works too.
    if rnd != 1:
        return
    emit(world, "draft", f"{team.full_name} select {player.name} at #{pick}",
         importance=MAJOR if pick <= 5 else NORMAL,
         tids=[team.tid], pids=[player.pid],
         detail=f"Round {rnd}, pick {pick}. {player.position}, {player.archetype}.")


def award(world: World, label: str, entry: dict) -> None:
    name = entry.get("name", "")
    if not name:
        return
    # Award entries carry per-game splits rather than a prebuilt line, so compose one here.
    bits = [f"{entry[k]} {lbl}" for k, lbl in (("ppg", "pts"), ("rpg", "reb"), ("apg", "ast"))
            if entry.get(k) is not None]
    detail = f"{entry.get('team', '')} · {', '.join(bits)}".strip(" ·")
    emit(world, "award", f"{name} wins {label}", importance=MAJOR,
         tids=[entry["tid"]] if entry.get("tid") is not None else [],
         pids=[entry["pid"]] if entry.get("pid") is not None else [],
         detail=detail)


def champion(world: World, team) -> None:
    emit(world, "award", f"{team.full_name} win the championship",
         importance=MAJOR, tids=[team.tid])


# Career marks worth a headline. The lower rungs of each ladder (5,000 points, 500 games) are
# crossed by dozens of players a year and read as filler; the wire only carries the ones that
# actually mean something.
_MILESTONE_FLOOR = {"pts": 15000, "reb": 10000, "ast": 7500, "gp": 1000}


def milestone(world: World, ms: dict) -> None:
    """A career milestone. ``ms`` is legacy.crossed_milestones' {stat, noun, value} plus a name."""
    stat, value = ms.get("stat", ""), ms.get("value", 0)
    if value < _MILESTONE_FLOOR.get(stat, 0):
        return
    noun = ms.get("noun", stat)
    emit(world, "milestone",
         f"{ms.get('name', '')} reaches {value:,} career {noun}s",
         importance=MAJOR, pids=[ms["pid"]] if ms.get("pid") is not None else [])


def hall_of_fame(world: World, snap: dict) -> None:
    emit(world, "milestone", f"{snap.get('name', '')} is inducted into the Hall of Fame",
         importance=MAJOR, pids=[snap["pid"]] if snap.get("pid") is not None else [])


def retirement(world: World, player) -> None:
    emit(world, "milestone", f"{player.name} announces his retirement",
         importance=NORMAL, pids=[player.pid],
         detail=f"{player.age} years old.")


def coach_fired(world: World, entry: dict) -> None:
    emit(world, "coaching", f"{entry['team']} part ways with {entry['coach']}",
         importance=NORMAL, tids=[entry["tid"]],
         detail=f"Finished {entry['record']} after {entry['seasons']} season"
                f"{'s' if entry['seasons'] != 1 else ''}.")


def coach_hired(world: World, entry: dict) -> None:
    career = f"Career record {entry['record']}." if entry["seasons"] else "His first head job."
    emit(world, "coaching", f"{entry['team']} hire {entry['coach']}",
         importance=NORMAL, tids=[entry["tid"]], detail=career)
