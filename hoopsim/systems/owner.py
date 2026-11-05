"""The owner: a mandate for the user's team each season, a confidence meter, and the sack.

AI front offices are judged by the coaching carousel; this is the same idea pointed at the user,
who is the general manager. Each preseason the owner reads the roster against the league and sets
a goal: a contender is expected to go deep, a rebuild only to be competitive. At season's end
confidence moves by how the team did against that goal, and a GM who keeps missing gets fired and
has to take a job somewhere worse.

NBA only. State lives on ``world.owner`` as a JSON-native dict so it saves with the career.
"""
from __future__ import annotations

from typing import List, Optional

from hoopsim.models.league import conference_standings
from hoopsim.models.world import World

START_CONFIDENCE = 60          # a new hire gets the benefit of the doubt
NEW_JOB_CONFIDENCE = 55        # a GM hired after being fired elsewhere gets a little less
FIRE_BELOW = 20                # confidence under this after a review ends the job
HONEYMOON_SEASONS = 1          # judged gently, and never fired, in the first season

# Expected regular season by preseason talent rank, fit to simulated seasons (8 seeds, 82 games):
# the most talented roster wins ~77% and the least ~22%, close to linear in between.
EXPECTED_BEST, EXPECTED_WORST = 0.76, 0.24
# Points of confidence per point of win percentage above or below expectation (8 wins ~ 12 pts).
WIN_PCT_WEIGHT = 120
# Points per postseason level above or below the mandate, capped either way.
LEVEL_WEIGHT = 8
LEVEL_CAP = 20
TITLE_BONUS = 10
TAX_PENALTY = 5                # paid the luxury tax and still missed the goal
DELTA_MIN, DELTA_MAX = -35, 20     # trust is lost faster than it is earned
OFFER_COUNT = 3

# Postseason levels: how far the team got.
MISSED, PLAY_IN, PLAYOFFS, WON_ROUND, CONF_FINALS, FINALS, CHAMPION = range(7)
LEVEL_LABELS = ["Missed the postseason", "Reached the play-in", "Made the playoffs",
                "Won a playoff series", "Reached the conference finals", "Reached the Finals",
                "Won the championship"]
_ROUND_LEVEL = {"R1": PLAYOFFS, "R2": WON_ROUND, "CF": CONF_FINALS, "Finals": FINALS}

# (best preseason rank in this tier, postseason target, mandate wording); rank 0 is the best roster.
_MANDATES = [
    (0, FINALS, "Reach the Finals"),
    (3, CONF_FINALS, "Reach the conference finals"),
    (8, WON_ROUND, "Win a playoff series"),
    (14, PLAYOFFS, "Make the playoffs"),
    (20, PLAY_IN, "Reach the play-in"),
    (25, MISSED, "Rebuild: stay competitive and develop"),
]


def _active(world: World) -> bool:
    return world.mode == "nba" and world.user_team_id is not None


def _talent_rank(world: World, tid: int) -> int:
    from hoopsim.sim import power
    strength = power.projected_strength(world)
    order = sorted(strength, key=lambda t: strength[t], reverse=True)
    return order.index(tid)


def make_mandate(world: World) -> dict:
    """This season's goal for the user's team, from where its roster ranks league-wide."""
    rank = _talent_rank(world, world.user_team_id)
    n = max(2, len(world.teams))
    target, label = next((t, lbl) for lo, t, lbl in reversed(_MANDATES) if rank >= lo)
    expected = EXPECTED_BEST - (EXPECTED_BEST - EXPECTED_WORST) * rank / (n - 1)
    return {"year": world.season_year, "rank": rank + 1, "target": target, "label": label,
            "expected_win_pct": round(expected, 3),
            "expected_wins": round(expected * world.season_games)}


def ensure(world: World) -> Optional[dict]:
    """The owner state for the user's current job, creating it (and this season's mandate) if
    missing. Older saves pick it up on first use."""
    if not _active(world):
        return None
    state = world.owner
    if state is None or state.get("tid") != world.user_team_id:
        state = world.owner = {"tid": world.user_team_id, "confidence": START_CONFIDENCE,
                               "seasons": 0, "mandate": None, "history": [],
                               "fired": False, "offers": []}
    if not state["fired"] and (state["mandate"] is None
                               or state["mandate"]["year"] != world.season_year):
        state["mandate"] = make_mandate(world)
    return state


def begin_season(world: World) -> None:
    """Set the new season's mandate. Call once the new season's rosters are in place."""
    ensure(world)


def standing(confidence: int) -> str:
    if confidence >= 70:
        return "Secure"
    if confidence >= 45:
        return "Stable"
    if confidence >= FIRE_BELOW + 5:
        return "Under pressure"
    return "Hot seat"


def postseason_level(world: World, tid: int) -> int:
    """How far ``tid`` got this season, from the bracket and conference standings."""
    bracket = world.bracket or {}
    if bracket.get("champion") == tid:
        return CHAMPION
    level = MISSED
    for s in bracket.get("all_series", []):
        if tid in (s["hi"], s["lo"]):
            level = max(level, _ROUND_LEVEL.get(s["round"], PLAYOFFS))
    if level == MISSED:
        team = world.teams[tid]
        order = conference_standings(world.team_list(), team.conference)
        if order.index(team) < 10:
            level = PLAY_IN
    return level


def _delta(world: World, state: dict, level: int) -> int:
    team = world.teams[state["tid"]]
    mandate = state["mandate"]
    delta = (team.win_pct - mandate["expected_win_pct"]) * WIN_PCT_WEIGHT
    gap = level - mandate["target"]
    if mandate["target"] > MISSED or gap > 0:       # a rebuild isn't marked down for missing
        delta += max(-LEVEL_CAP, min(LEVEL_CAP, gap * LEVEL_WEIGHT))
    if level == CHAMPION:
        delta += TITLE_BONUS
    from hoopsim.systems import cap
    if gap < 0 and cap.luxury_tax(world, team) > 0:
        delta -= TAX_PENALTY
    delta = max(DELTA_MIN, min(DELTA_MAX, delta))
    if delta < 0 and state["seasons"] < HONEYMOON_SEASONS:
        delta /= 2                                  # a new GM inherited this roster
    return int(round(delta))


def review_season(world: World) -> Optional[dict]:
    """Judge the season just finished. Call after the playoffs, before rosters change.

    Returns the review (also appended to the owner's history), or ``None`` outside NBA mode.
    """
    state = ensure(world)
    if state is None or state["fired"]:
        return None
    if state["history"] and state["history"][-1]["year"] == world.season_year:
        return state["history"][-1]                 # already reviewed (a refreshed page)
    team = world.teams[state["tid"]]
    level = postseason_level(world, team.tid)
    delta = _delta(world, state, level)
    before = state["confidence"]
    state["confidence"] = max(0, min(100, before + delta))
    state["seasons"] += 1
    mandate = state["mandate"]
    fired = state["confidence"] < FIRE_BELOW and state["seasons"] > HONEYMOON_SEASONS
    review = {"year": world.season_year, "record": team.record_str, "level": level,
              "result": LEVEL_LABELS[level], "goal": mandate["label"],
              "expected_wins": mandate["expected_wins"], "met": level >= mandate["target"],
              "before": before, "delta": delta, "confidence": state["confidence"],
              "fired": fired}
    state["history"].append(review)
    if fired:
        state["fired"] = True
        state["offers"] = job_offers(world)
        from hoopsim.systems import news
        news.emit(world, "coaching", f"{team.full_name} fire their general manager",
                  importance=news.MAJOR, tids=[team.tid],
                  detail=f"Finished {team.record_str}; the owner wanted: {mandate['label'].lower()}.")
    return review


def job_offers(world: World) -> List[int]:
    """Teams willing to hire a GM who just got fired: strugglers, picked at random."""
    others = [t for t in world.team_list() if t.tid != world.user_team_id]
    others.sort(key=lambda t: t.win_pct)
    pool = [t.tid for t in others[:max(OFFER_COUNT, len(others) // 2)]]
    return sorted(world.rng.sample(pool, min(OFFER_COUNT, len(pool))))


def take_job(world: World, tid: int) -> None:
    """Move the user to a new team after a firing. The old team reverts to AI control."""
    state = world.owner
    if state is None or not state["fired"] or tid not in state["offers"]:
        raise ValueError("That job isn't on offer.")
    old = world.teams[world.user_team_id]
    old.block_list = []
    old.rotation = []               # drop the user's pinned rotation; the AI picks its own
    old.auto_lineup = True
    world.trade_offers = []
    world.user_team_id = tid
    world.owner = {"tid": tid, "confidence": NEW_JOB_CONFIDENCE, "seasons": 0, "mandate": None,
                   "history": [], "fired": False, "offers": [],
                   "past_jobs": state.get("past_jobs", []) + [
                       {"tid": state["tid"], "seasons": state["seasons"],
                        "history": state["history"]}]}
    ensure(world)


def view(world: World) -> Optional[dict]:
    """What the UI shows: the mandate, confidence and how the season is tracking."""
    state = ensure(world)
    if state is None:
        return None
    team = world.teams[state["tid"]]
    mandate = state["mandate"]
    out = {"confidence": state["confidence"], "standing": standing(state["confidence"]),
           "seasons": state["seasons"], "mandate": mandate, "fired": state["fired"],
           "offers": list(state["offers"]),
           "last_review": state["history"][-1] if state["history"] else None,
           "honeymoon": state["seasons"] < HONEYMOON_SEASONS}
    if mandate and team.games_played >= 10:
        pace = team.win_pct - mandate["expected_win_pct"]
        out["pace"] = ("ahead" if pace > 0.04 else "behind" if pace < -0.04 else "on track")
        out["pace_wins"] = round(team.win_pct * world.season_games)
    return out
