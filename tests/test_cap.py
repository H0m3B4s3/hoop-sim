"""Salary-cap, trade, and free-agency system tests."""
from __future__ import annotations

from hoopr.config import ROSTER_MAX, SALARY_CAP, VETERAN_MINIMUM
from hoopr.gen.leaguegen import build_world
from hoopr.systems import cap, freeagency
from hoopr.systems.trades import TradeOffer, ai_evaluates, execute_trade, validate_trade


def test_max_salary_increases_with_experience():
    assert cap.max_salary(0) < cap.max_salary(7) <= cap.max_salary(10)


def test_market_salary_bounds():
    w = build_world(seed=1)
    for p in w.players.values():
        m = cap.market_salary(p)
        assert VETERAN_MINIMUM <= m <= cap.max_salary(p.experience)


def test_trade_matching_rule():
    # over the cap (no space): can take 125% + buffer
    assert cap.trade_matching_ok(0, 10_000_000, 12_000_000)
    assert not cap.trade_matching_ok(0, 10_000_000, 15_000_000)
    # cap space lets a team absorb more
    assert cap.trade_matching_ok(20_000_000, 5_000_000, 24_000_000)


def test_can_sign_rules():
    w = build_world(seed=2)
    team = w.teams[0]
    # minimum is always allowed when there is a roster spot
    while len(team.roster) > ROSTER_MAX - 1:
        team.roster.pop()
    ok, _ = cap.can_sign(w, team, VETERAN_MINIMUM)
    assert ok
    # a full roster cannot sign anyone
    full = w.teams[1]
    while len(full.roster) < ROSTER_MAX:
        full.roster.append(-len(full.roster))
    assert not cap.can_sign(w, full, VETERAN_MINIMUM)[0]


def _matched_pair(world, a, b):
    for pa in a.roster:
        for pb in b.roster:
            sa = world.players[pa].contract.current_salary
            sb = world.players[pb].contract.current_salary
            if abs(sa - sb) < 1_500_000 and min(sa, sb) > VETERAN_MINIMUM:
                if abs(world.players[pa].overall - world.players[pb].overall) >= 5:
                    return pa, pb
    return None, None


def test_trade_validation_and_ai_direction():
    w = build_world(seed=5)
    a, b = w.teams[0], w.teams[1]
    pa, pb = _matched_pair(w, a, b)
    assert pa is not None, "no matched salary pair found for test seed"
    # orient so B receives the better player
    if w.players[pa].overall < w.players[pb].overall:
        pa, pb = pb, pa  # ensure pa (from a) is the better one
        # pa must belong to a; re-find if swapped across teams
    # rebuild proper membership: pick better-overall from whichever team
    better = max((pa, pb), key=lambda pid: w.players[pid].overall)
    worse = min((pa, pb), key=lambda pid: w.players[pid].overall)
    a_pid = better if better in a.roster else worse
    b_pid = worse if a_pid == better else better
    offer = TradeOffer(a.tid, b.tid, [a_pid], [b_pid])
    legal, _ = validate_trade(w, offer)
    assert legal
    # the team receiving the more valuable player should be happier
    recv_better = b.tid if w.players[a_pid].overall > w.players[b_pid].overall else a.tid
    accepts_good, _ = ai_evaluates(w, offer, recv_better)
    assert accepts_good


def test_execute_trade_moves_players():
    w = build_world(seed=8)
    a, b = w.teams[0], w.teams[1]
    pa, pb = _matched_pair(w, a, b)
    assert pa is not None
    offer = TradeOffer(a.tid, b.tid, [pa], [pb])
    assert validate_trade(w, offer)[0]
    execute_trade(w, offer)
    assert pa in b.roster and w.players[pa].team_id == b.tid
    assert pb in a.roster and w.players[pb].team_id == a.tid
    assert pa not in a.roster and pb not in b.roster


def test_cap_grows_each_offseason():
    w = build_world(seed=12)
    before = w.salary_cap
    cap.grow_cap(w, 0.035)
    assert w.salary_cap > before
    assert w.luxury_tax_line > 170_000_000
    # cap functions read the live value
    team = w.teams[0]
    assert cap.cap_space(w, team) == max(0, w.salary_cap - cap.payroll(w, team))


def test_extend_contract():
    w = build_world(seed=13)
    team = w.teams[0]
    pid = team.roster[0]
    p = w.players[pid]
    years_before = p.contract.years_remaining
    ok, _ = cap.extend_contract(w, team, pid, cap.market_salary(p), 2)
    assert ok
    assert p.contract.years_remaining == years_before + 2
    # cannot exceed the max contract length
    from hoopr.config import MAX_CONTRACT_YEARS
    p.contract.salaries = [10_000_000] * MAX_CONTRACT_YEARS
    p.contract.guaranteed = [True] * MAX_CONTRACT_YEARS
    ok2, _ = cap.extend_contract(w, team, pid, 10_000_000, 1)
    assert not ok2
    # cannot exceed the max salary
    ok3, _ = cap.extend_contract(w, w.teams[1], w.teams[1].roster[0], 999_000_000, 1)
    assert not ok3


def test_capped_out_team_cannot_sign_star_for_minimum():
    from hoopr.config import MID_LEVEL_EXCEPTION
    w = build_world(seed=1)
    team = w.teams[0]
    # release the league's best player to free agency
    star = max(w.players.values(), key=lambda p: p.overall)
    if star.team_id is not None:
        w.release_player(star.pid)
    assert cap.market_salary(star) > MID_LEVEL_EXCEPTION      # a genuine max-type free agent
    # cap the team well over the salary cap
    for pid in team.roster:
        w.players[pid].contract.salaries = [20_000_000] + w.players[pid].contract.salaries[1:]
    assert cap.cap_space(w, team) == 0
    # the offer is the player's market price, never silently the minimum
    sal, _ = freeagency.offer_for(w, team, star)
    assert sal == cap.market_salary(star)
    # the old bug: signing the star for the veteran minimum must be rejected
    ok_min, _ = freeagency.sign_free_agent(w, team, star.pid, VETERAN_MINIMUM, 1)
    assert not ok_min
    # and a max deal can't fit with no cap room
    ok_mkt, _ = freeagency.sign_free_agent(w, team, star.pid, cap.market_salary(star), 4)
    assert not ok_mkt
    assert star.team_id is None                              # still a free agent


def test_mid_level_exception_limited_to_once_per_offseason():
    from hoopr.config import MID_LEVEL_EXCEPTION
    w = build_world(seed=1)
    team = w.teams[0]
    # cap the team well over the salary cap and open a couple of roster spots
    for pid in team.roster:
        w.players[pid].contract.salaries = [20_000_000] + w.players[pid].contract.salaries[1:]
    while len(team.roster) > ROSTER_MAX - 3:
        team.roster.pop()
    assert cap.cap_space(w, team) == 0

    # two free agents whose market sits inside the mid-level band
    band = [p for p in w.players.values()
            if VETERAN_MINIMUM < cap.market_salary(p) <= MID_LEVEL_EXCEPTION
            and p.team_id is not None and p.team_id != team.tid]
    fa1, fa2 = band[0], band[1]
    w.release_player(fa1.pid)
    w.release_player(fa2.pid)

    # the first mid-level signing succeeds and spends the exception
    ok1, _ = freeagency.sign_free_agent(w, team, fa1.pid, cap.market_salary(fa1), 2)
    assert ok1 and team.mle_used
    # a second mid-level signing is now rejected (only one MLE per offseason)
    ok2, _ = freeagency.sign_free_agent(w, team, fa2.pid, cap.market_salary(fa2), 2)
    assert not ok2 and fa2.team_id is None
    # a veteran-minimum deal is still always available
    assert cap.can_sign(w, team, VETERAN_MINIMUM)[0]


def test_free_agency_signs_players():
    w = build_world(seed=3)
    w.user_team_id = 0
    # open up roster spots (as expiring contracts would in the offseason)
    for tid in range(2, 10):
        team = w.teams[tid]
        for pid in list(team.roster)[-2:]:
            w.release_player(pid)
    before = len(w.free_agents)
    summary = freeagency.run_free_agency(w)
    assert summary["signings"] > 0
    assert len(w.free_agents) < before
    # signed players now belong to a (non-user) team and are cap-legal
    for t in w.team_list():
        assert cap.payroll(w, t) < SALARY_CAP * 1.6
