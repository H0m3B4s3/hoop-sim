"""Free-agent negotiation: years and money trade off, instead of auto-accept at the asking price."""
from __future__ import annotations

from hoopsim.config import MAX_CONTRACT_YEARS, SALARY_CAP
from hoopsim.gen.leaguegen import build_world
from hoopsim.systems import freeagency as FA


def _fa(world, *, overall=None, age=None):
    """A free agent matching optional overall/age filters (closest by overall)."""
    pool = world.free_agent_players()
    if age is not None:
        pool = [p for p in pool if abs(p.age - age) <= 1] or pool
    if overall is not None:
        return min(pool, key=lambda p: abs(p.overall - overall))
    return max(pool, key=lambda p: p.overall)


def _spacious_team(world):
    """A team with cap room so cap legality never masks a willingness check."""
    from hoopsim.systems import cap
    return max(world.team_list(), key=lambda t: cap.cap_space(world, t))


def test_meeting_ask_at_preferred_years_accepts():
    w = build_world(seed=1)
    p = _fa(w)
    pref = FA.contract_years_for(p)
    ask = FA.wave_market_salary(w, p)
    ok, _ = FA.evaluate_offer(w, p, ask, pref)
    assert ok


def test_underpaying_at_preferred_years_is_rejected():
    w = build_world(seed=1)
    p = _fa(w, overall=80)
    pref = FA.contract_years_for(p)
    ask = FA.wave_market_salary(w, p)
    ok, why = FA.evaluate_offer(w, p, ask - 3_000_000, pref)
    assert not ok and "wants about" in why


def test_extra_years_lower_the_required_salary():
    """Offering more years than preferred is security the player discounts for."""
    w = build_world(seed=2)
    p = _fa(w, overall=78)
    pref = FA.contract_years_for(p)
    if pref >= MAX_CONTRACT_YEARS:
        return
    base = FA.required_salary(w, p, pref)
    longer = FA.required_salary(w, p, pref + 1)
    assert longer < base
    # the cheaper, longer deal is accepted at a salary the preferred-length deal would reject
    assert FA.evaluate_offer(w, p, longer, pref + 1)[0]
    assert not FA.evaluate_offer(w, p, longer, pref)[0]


def test_short_deal_demands_a_premium():
    """Fewer years than preferred makes the player hold out for more per season."""
    w = build_world(seed=2)
    p = _fa(w, overall=82, age=33)         # a vet who prefers a short deal already
    pref = FA.contract_years_for(p)
    if pref <= 1:
        p = _fa(w, overall=80, age=28)
        pref = FA.contract_years_for(p)
    shorter = FA.required_salary(w, p, pref - 1)
    base = FA.required_salary(w, p, pref)
    assert shorter > base


def test_lesser_free_agents_are_more_flexible_on_term():
    """The security discount for extra years is larger for lesser FAs than for stars."""
    w = build_world(seed=3)
    star = _fa(w, overall=88, age=27)
    fringe = _fa(w, overall=68, age=27)

    def discount(p):
        pref = FA.contract_years_for(p)
        y = min(MAX_CONTRACT_YEARS, pref + 1)
        if y == pref:
            return 0.0
        base = FA.required_salary(w, p, pref)
        return (base - FA.required_salary(w, p, y)) / base

    assert discount(fringe) > discount(star)


def test_sign_free_agent_uses_negotiation():
    w = build_world(seed=4)
    team = _spacious_team(w)
    p = _fa(w, overall=72)
    pref = FA.contract_years_for(p)
    ask = FA.wave_market_salary(w, p)
    # underpay at preferred length → rejected on willingness, player stays a FA
    ok, _ = FA.sign_free_agent(w, team, p.pid, ask - 2_000_000, pref)
    assert not ok and p.is_free_agent
    # fair offer at preferred length → signs
    ok, _ = FA.sign_free_agent(w, team, p.pid, ask, pref)
    assert ok and p.team_id == team.tid


def test_year_bounds_rejected():
    w = build_world(seed=5)
    p = _fa(w)
    assert not FA.evaluate_offer(w, p, 50_000_000, 0)[0]
    assert not FA.evaluate_offer(w, p, 50_000_000, MAX_CONTRACT_YEARS + 1)[0]
