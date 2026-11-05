"""How a player feels about re-signing with the user's team.

Extensions used to be a formality: any player took any offer. Now a player weighs whether the team
wins, whether he gets the role his talent earns, how long he has been there, and (quietly) his
morale. An eager player gives a hometown discount, a sour one wants a raise, and a player who has
decided to test free agency won't extend at all, with the reason spelled out.

This only governs the user's extensions. AI clubs keep re-signing through
``freeagency.run_retention`` unchanged, and morale itself stays a background mechanic: willingness
is only shown when the user acts on a contract.
"""
from __future__ import annotations

from typing import List

from hoopsim.models.team import roster_players
from hoopsim.models.world import World

EAGER, OPEN, WANTS_MORE, TESTING_FA = "eager", "open", "wants_more", "testing_fa"
LABELS = {EAGER: "Eager to stay", OPEN: "Open to an extension",
          WANTS_MORE: "Wants a better deal", TESTING_FA: "Plans to test free agency"}
# Share of market value each stance asks the user for. A player testing free agency won't extend.
ASK_FACTOR = {EAGER: 0.95, OPEN: 1.0, WANTS_MORE: 1.15}
EAGER_FROM, OPEN_FROM, WANTS_MORE_FROM = 0.6, -0.2, -0.8

MIN_GAMES = 10                 # before this, a season's record and minutes say little
# Minutes a player expects by where his talent ranks on the roster (index 0 = best player).
EXPECTED_MPG = [34, 32, 30, 28, 26, 22, 20, 17, 14, 12]
MORALE_WEIGHT = 0.5
LOYAL_YEARS = 3


def _talent_rank(world: World, team, player) -> int:
    ranked = sorted(roster_players(team, world.players), key=lambda p: p.overall, reverse=True)
    return next(i for i, p in enumerate(ranked) if p.pid == player.pid)


def _winning(world: World, team) -> float:
    """-1 (a loser) .. +1 (a powerhouse), from the record, or the roster before the record means much."""
    if team.games_played >= MIN_GAMES:
        return max(-1.0, min(1.0, (team.win_pct - 0.5) * 2.5))
    from hoopsim.sim import power
    return (power.strength_stars(world)[team.tid] - 3) / 2.0


def assess(world: World, player) -> dict:
    """The player's stance on extending with his current (the user's) team, and why."""
    team = world.teams[player.team_id]
    score, reasons = 0.0, []

    win = _winning(world, team)
    win_weight = 1.5 if player.age >= 29 else 0.6 if player.age <= 24 else 1.0
    score += win * win_weight
    if win <= -0.3:
        reasons.append("wants to play for a winner" if player.age >= 29
                       else "is tired of losing")
    elif win >= 0.3:
        reasons.append("likes where the team is headed")

    if player.season.gp >= MIN_GAMES and not player.is_injured:
        rank = _talent_rank(world, team, player)
        expected = EXPECTED_MPG[min(rank, len(EXPECTED_MPG) - 1)]
        gap = (player.season.mpg - expected) / 10.0
        role = max(-1.0, min(0.5, gap)) * (1.3 if player.age <= 25 else 1.0)
        score += role
        if gap <= -0.5:
            reasons.append(f"wants a bigger role ({player.season.mpg:.0f} mpg as the team's "
                           f"#{rank + 1} talent)")
        elif gap >= 0.3:
            reasons.append("is happy with his role")

    years = player.contract.years_with_team
    if years >= LOYAL_YEARS:
        score += 0.3 if years < 5 else 0.5
        reasons.append(f"is loyal after {years} seasons here")

    score += max(-1.0, min(1.0, (player.morale - 70) / 30.0)) * MORALE_WEIGHT

    level = (EAGER if score >= EAGER_FROM else OPEN if score >= OPEN_FROM
             else WANTS_MORE if score >= WANTS_MORE_FROM else TESTING_FA)
    return {"level": level, "label": LABELS[level], "score": round(score, 2),
            "reasons": reasons, "ask_factor": ASK_FACTOR.get(level)}


def describe(name: str, mood: dict) -> str:
    """One readable sentence: the stance plus its main reasons."""
    reasons: List[str] = mood["reasons"]
    why = (" — he " + ", and ".join(reasons[:2])) if reasons else ""
    return f"{name}: {mood['label'].lower()}{why}."
