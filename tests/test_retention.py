"""AI re-signing (retention) tests — see #5 in the pain-point triage.

AI teams should keep their good expiring players via Bird rights rather than letting every
contract walk to free agency, so only genuinely available talent reaches the market.
"""
from __future__ import annotations

from hoopsim.config import VETERAN_MINIMUM
from hoopsim.gen.leaguegen import build_world
from hoopsim.models.contract import flat_contract
from hoopsim.sim import playoffs as P
from hoopsim.sim import season as S
from hoopsim.systems import freeagency, offseason


def _expiring(world, pid, salary):
    world.players[pid].contract = flat_contract(salary, 1, world.season_year)


def test_retention_resigns_expiring_star():
    w = build_world(seed=7)
    w.user_team_id = -1                       # exclude no real team
    team = w.teams[0]
    star = max(team.roster, key=lambda pid: w.players[pid].overall)
    _expiring(w, star, 20_000_000)
    res = freeagency.run_retention(w)
    assert res["resigned"] >= 1
    # the star keeps playing for the team beyond their expiring year
    assert w.players[star].contract.years_remaining > 1
    assert star in team.roster


def test_retention_excludes_user_team():
    w = build_world(seed=7)
    team = w.teams[0]
    w.user_team_id = team.tid
    star = max(team.roster, key=lambda pid: w.players[pid].overall)
    _expiring(w, star, 20_000_000)
    freeagency.run_retention(w)
    # the user decides their own re-signings; the AI never auto-extends the user's players
    assert w.players[star].contract.years_remaining == 1


def test_retention_keeps_stars_off_the_market():
    """Through a full pre-draft, an AI team's best expiring player should not reach free agency."""
    w = build_world(seed=3)
    w.user_team_id = 1
    w.season_games = 10
    S.start_season(w)
    while not S.regular_season_complete(w):
        S.advance_one_day(w)
    P.start_playoffs(w)
    while not P.playoffs_complete(w):
        P.advance_playoff_slate(w)

    team = w.teams[0]                          # an AI team
    star = max(team.roster, key=lambda pid: w.players[pid].overall)
    _expiring(w, star, 24_000_000)

    summary = offseason.pre_draft(w, P.champion(w))
    assert summary["resigned"] > 0
    assert star not in w.free_agents           # the star was retained, not let walk
    assert w.players[star].team_id == team.tid


def test_retention_lets_min_filler_walk():
    w = build_world(seed=9)
    w.user_team_id = -1
    team = w.teams[0]
    # an end-of-bench, minimum-salary veteran with no upside should be allowed to walk
    fringe = min(
        (pid for pid in team.roster if w.players[pid].age >= 30),
        key=lambda pid: w.players[pid].overall,
        default=min(team.roster, key=lambda pid: w.players[pid].overall),
    )
    _expiring(w, fringe, VETERAN_MINIMUM)
    before = w.players[fringe].contract.years_remaining
    freeagency.run_retention(w)
    assert w.players[fringe].contract.years_remaining == before
