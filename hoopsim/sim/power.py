"""Team power ratings — a single "where do we stand" number per team.

Two ingredients are blended into one net rating (points better/worse than an average team on a
neutral floor, the same scale as ESPN's BPI or a Simple Rating System):

* **SRS** — a results-based Simple Rating System solved from games actually played:
  ``rating = average_margin + average_opponent_rating``. This is strength-of-schedule adjusted,
  so beating good teams counts more than padding a record against cupcakes.
* **Roster prior** — a talent estimate from the rotation's ratings. Early in the season the
  sample of games is tiny and noisy, so the prior anchors the number; its weight decays as games
  accumulate. This is what lets the user judge a 5-3 team that has played nobody against a 3-5
  team that has played a gauntlet *in week two*, which is exactly when trade season heats up.

The output is league-relative: ratings are de-meaned so the league always averages 0.0.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from hoopsim.models.team import rotation_pool
from hoopsim.models.world import World

# Cap on per-game margin fed into SRS: a 40-point blowout shouldn't count four times a 10-point
# win. Garbage time is noise, not signal.
_MARGIN_CAP = 18.0
# Games-played half-life for trusting results over the roster prior. At gp == _RESULTS_K the
# blend is 50/50; by a full 82-game season results dominate (~0.85 weight).
_RESULTS_K = 14.0
# Points of net rating per standard deviation of rotation talent. Keeps the prior's spread
# sensible (~±6-9 pts at the extremes) regardless of the league's absolute rating inflation.
_PRIOR_SPREAD = 5.0


@dataclass
class PowerRating:
    tid: int
    power: float        # blended net rating (points vs an average team), league-mean 0
    srs: float          # results-only Simple Rating System (0 until games are played)
    prior: float        # roster-talent prior (net points)
    sos: float          # strength of schedule: average opponent power faced
    rank: int = 0       # 1 = best in league
    proj_win_pct: float = 0.0


# ---------------------------------------------------------------------------
# Roster-talent prior
# ---------------------------------------------------------------------------
def _team_talent(world: World, team) -> float:
    """Minutes-weighted overall of the rotation — a single talent scalar for the roster."""
    pool = rotation_pool(team, world.players)
    if not pool:
        return 70.0
    # Heavier weight on the best players (stars swing games more than the 9th man).
    weights = [max(1.0, 10.0 - i) for i in range(len(pool))]
    total = sum(p.overall * w for p, w in zip(pool, weights))
    return total / sum(weights)


def roster_priors(world: World) -> Dict[int, float]:
    """Net-rating prior per team from rotation talent, standardized across the league."""
    teams = world.team_list()
    talents = {t.tid: _team_talent(world, t) for t in teams}
    vals = list(talents.values())
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    std = var ** 0.5 or 1.0
    return {tid: (t - mean) / std * _PRIOR_SPREAD for tid, t in talents.items()}


# ---------------------------------------------------------------------------
# Results-based SRS
# ---------------------------------------------------------------------------
def _regular_games(world: World):
    return [g for g in world.schedule if g.played and not g.is_playoff]


def compute_srs(world: World) -> Dict[int, float]:
    """Solve the Simple Rating System via fixed-point iteration over played regular games."""
    teams = world.team_list()
    margins: Dict[int, List[float]] = {t.tid: [] for t in teams}
    opps: Dict[int, List[int]] = {t.tid: [] for t in teams}
    for g in _regular_games(world):
        diff = g.home_score - g.away_score
        capped = max(-_MARGIN_CAP, min(_MARGIN_CAP, diff))
        margins[g.home].append(capped)
        opps[g.home].append(g.away)
        margins[g.away].append(-capped)
        opps[g.away].append(g.home)

    avg_margin = {tid: (sum(m) / len(m) if m else 0.0) for tid, m in margins.items()}
    rating = dict(avg_margin)
    for _ in range(50):
        nxt = {}
        for tid in rating:
            opp = opps[tid]
            sos = sum(rating[o] for o in opp) / len(opp) if opp else 0.0
            nxt[tid] = avg_margin[tid] + sos
        # De-mean each pass so the system stays anchored at 0 and converges cleanly.
        m = sum(nxt.values()) / len(nxt)
        rating = {tid: v - m for tid, v in nxt.items()}
    return rating, opps


# ---------------------------------------------------------------------------
# Blended power ratings
# ---------------------------------------------------------------------------
def _win_pct_from_net(net: float) -> float:
    """Pythagorean-style map from net rating to an expected win percentage."""
    # ~2.7 net points ≈ one extra win per ~8 games; logistic keeps it in (0,1).
    import math
    return 1.0 / (1.0 + math.exp(-net / 6.5))


def power_ratings(world: World) -> List[PowerRating]:
    """One :class:`PowerRating` per team, ranked best-first."""
    priors = roster_priors(world)
    srs, opps = compute_srs(world)
    teams = world.team_list()
    gp = {t.tid: t.games_played for t in teams}

    blended: Dict[int, float] = {}
    for t in teams:
        w = gp[t.tid] / (gp[t.tid] + _RESULTS_K)
        blended[t.tid] = w * srs[t.tid] + (1 - w) * priors[t.tid]
    # Re-center the blend so the league mean is exactly 0.
    m = sum(blended.values()) / len(blended)
    blended = {tid: v - m for tid, v in blended.items()}

    out: List[PowerRating] = []
    for t in teams:
        opp = opps[t.tid]
        sos = sum(blended[o] for o in opp) / len(opp) if opp else 0.0
        out.append(PowerRating(
            tid=t.tid,
            power=blended[t.tid],
            srs=srs[t.tid],
            prior=priors[t.tid],
            sos=sos,
            proj_win_pct=_win_pct_from_net(blended[t.tid]),
        ))
    out.sort(key=lambda r: r.power, reverse=True)
    for i, r in enumerate(out, start=1):
        r.rank = i
    return out


def power_map(world: World) -> Dict[int, PowerRating]:
    return {r.tid: r for r in power_ratings(world)}


# ---------------------------------------------------------------------------
# Preseason team strength (for team selection, before any games are played)
# ---------------------------------------------------------------------------
def projected_strength(world: World) -> Dict[int, int]:
    """A single projected-rating number per team: the minutes-weighted rotation overall, rounded.

    Unlike :func:`power_ratings`, this needs no games played — it's the roster-talent read used to
    rank franchises on the team-selection screen."""
    return {t.tid: round(_team_talent(world, t)) for t in world.team_list()}


def strength_stars(world: World) -> Dict[int, int]:
    """1–5 stars by where each team's projected strength ranks league-wide (even quintiles).

    Rank-based so the stars always spread across the league instead of clustering — a team is
    judged relative to its peers, not against an absolute scale."""
    talents = {t.tid: _team_talent(world, t) for t in world.team_list()}
    order = sorted(talents, key=lambda tid: talents[tid])     # weakest first
    n = len(order) or 1
    return {tid: min(5, 1 + i * 5 // n) for i, tid in enumerate(order)}
