"""Tiered free agency and phased recruiting — markets resolve in waves.

NBA free agency opens in tiers (max-contract caliber first, then down), with unsigned players
re-pricing downward as the market cools. College Signing Day commits the top star tiers first,
leaving missed targets on the board for later waves.
"""
from __future__ import annotations

from hoopsim.gen.collegegen import build_college_world, star_rating
from hoopsim.gen.leaguegen import build_world
from hoopsim.systems import cap, freeagency, recruiting


# --- Tiered free agency ----------------------------------------------------
def _make_free_agent(world, pid):
    """Detach a player from any team and drop them into the free-agent pool."""
    p = world.players[pid]
    if p.team_id is not None and p.team_id in world.teams:
        world.teams[p.team_id].remove_player(pid)
    p.team_id = None
    if pid not in world.free_agents:
        world.free_agents.append(pid)


def test_natural_wave_orders_by_overall():
    w = build_world(seed=4)
    # pick representative players across the rating spectrum
    by_ovr = sorted(w.players.values(), key=lambda p: p.overall)
    low, high = by_ovr[0], by_ovr[-1]
    assert freeagency.natural_wave(high) <= freeagency.natural_wave(low)
    assert 0 <= freeagency.natural_wave(high) < freeagency.NUM_FA_WAVES


def test_wave_pool_widens_each_wave():
    w = build_world(seed=4)
    w.user_team_id = -1
    # everyone is a free agent so the pool is the whole league
    for pid in list(w.players):
        _make_free_agent(w, pid)
    freeagency.start_fa_market(w)
    sizes = []
    for _ in range(freeagency.NUM_FA_WAVES):
        sizes.append(len(freeagency.fa_wave_pool(w)))
        freeagency.advance_fa_wave(w)
    # each successive open tier includes at least as many players as the last
    assert sizes == sorted(sizes)
    assert sizes[-1] >= sizes[0]


def test_price_cools_as_a_player_goes_unsigned():
    w = build_world(seed=4)
    star = max(w.players.values(), key=lambda p: p.overall)
    _make_free_agent(w, star.pid)
    base = cap.market_salary(star)

    freeagency.end_fa_market(w)                       # market closed → full price
    assert freeagency.wave_market_salary(w, star) == base

    freeagency.start_fa_market(w)                     # wave 0, the star's own tier → full price
    assert freeagency.wave_market_salary(w, star) == base

    freeagency.advance_fa_wave(w)                     # the tier has sat a wave → cheaper
    cooled = freeagency.wave_market_salary(w, star)
    assert cooled < base
    assert cooled >= int(base * freeagency.MIN_DISCOUNT_FACTOR)


def test_cannot_lowball_below_the_cooled_price():
    w = build_world(seed=4)
    team = w.teams[0]
    w.user_team_id = team.tid
    star = max((w.players[pid] for pid in w.teams[1].roster), key=lambda p: p.overall)
    _make_free_agent(w, star.pid)
    freeagency.start_fa_market(w)
    ask = freeagency.wave_market_salary(w, star)
    ok, _ = freeagency.sign_free_agent(w, team, star.pid, ask - 1_000_000, 2)
    assert not ok                                     # below the asking price is rejected


def test_run_free_agency_clears_market_and_signs():
    w = build_world(seed=5)
    w.user_team_id = -1
    # free up a chunk of talent so AI teams have someone to sign
    for pid in list(w.teams[0].roster) + list(w.teams[1].roster):
        _make_free_agent(w, pid)
    res = freeagency.run_free_agency(w)
    assert res["signings"] >= 1
    assert w.fa_wave is None                          # headless run closes the market


# --- Phased recruiting -----------------------------------------------------
def test_recruit_wave_pool_widens_and_top_stars_first():
    w = build_college_world(seed=6, economy="scholarship")
    from hoopsim.gen.collegegen import generate_recruit_class
    generate_recruit_class(w)
    recruiting.start_recruiting(w)
    wave0 = recruiting.recruit_wave_pool(w)
    # the opening wave contains only recruits whose tier opens in wave 0
    assert all(recruiting.natural_recruit_wave(p) == 0 for p in wave0)
    sizes = []
    for _ in range(recruiting.NUM_RECRUIT_WAVES):
        sizes.append(len(recruiting.recruit_wave_pool(w)))
        recruiting.advance_recruit_wave(w)
    assert sizes == sorted(sizes)


def test_resolve_recruiting_resolves_all_waves():
    w = build_college_world(seed=6, economy="scholarship")
    from hoopsim.gen.collegegen import generate_recruit_class
    generate_recruit_class(w)
    # open up roster room (real flow frees spots via graduations) so programs can actually sign
    for team in w.team_list():
        for pid in list(team.roster)[:3]:
            team.remove_player(pid)
            w.players.pop(pid, None)
    assert len(w.recruit_players()) > 0
    res = recruiting.resolve_recruiting(w, {})
    assert res["total"] >= 1
    assert w.recruit_wave is None                     # market closed after the last wave
    assert w.recruits == []                           # uncommitted recruits leave the pool


def test_resolve_recruiting_wave_keeps_missed_recruits_on_the_board():
    w = build_college_world(seed=6, economy="scholarship")
    from hoopsim.gen.collegegen import generate_recruit_class
    generate_recruit_class(w)
    w.user_team_id = w.team_list()[0].tid
    recruiting.start_recruiting(w)
    # only wave-0 recruits could commit in the first wave; later tiers stay untouched
    later_tier = [p.pid for p in w.recruit_players() if recruiting.natural_recruit_wave(p) > 0]
    recruiting.resolve_recruiting_wave(w, {})         # resolve top tier with no user offers
    still_available = {p.pid for p in w.recruit_players()}
    assert all(pid in still_available for pid in later_tier)  # untouched lower tiers carry forward
