"""Shopping a draft pick for return packages (solicit_pick_offers)."""
from __future__ import annotations

from hoopsim.gen.leaguegen import build_world
from hoopsim.systems import draft_system as D
from hoopsim.systems import trades


def _world(seed=1):
    w = build_world(seed=seed)
    w.user_team_id = 1
    D.init_draft_picks(w)
    return w


def test_user_first_rounder_draws_offers():
    w = _world()
    user = w.user_team
    pick = next(p for p in w.picks_owned_by(user.tid) if p.round == 1)
    offers = trades.solicit_pick_offers(w, pick.key)
    assert offers, "a first-round pick should attract interest"
    for o in offers:
        assert o.offer.a == user.tid
        assert list(o.offer.a_picks) == [pick.key]   # user is sending the pick
        assert o.offer.b_sends or o.offer.b_picks     # getting something back
        assert trades.validate_trade(w, o.offer)[0]


def test_offers_sorted_by_value_desc():
    w = _world(seed=4)
    pick = next(p for p in w.picks_owned_by(w.user_team_id) if p.round == 1)
    offers = trades.solicit_pick_offers(w, pick.key)
    vals = [o.value for o in offers]
    assert vals == sorted(vals, reverse=True)


def test_cannot_shop_a_pick_you_do_not_own():
    w = _world(seed=2)
    # A pick belonging to another team, never traded to the user.
    other = next(t for t in w.team_list() if t.tid != w.user_team_id)
    foreign = next(p for p in w.picks_owned_by(other.tid))
    assert trades.solicit_pick_offers(w, foreign.key) == []


def test_executing_a_pick_offer_transfers_the_pick():
    w = _world(seed=7)
    user = w.user_team
    pick = next(p for p in w.picks_owned_by(user.tid) if p.round == 1)
    offers = trades.solicit_pick_offers(w, pick.key)
    assert offers
    offer = offers[0].offer
    trades.execute_trade(w, offer)
    moved = w.find_pick(*pick.key)
    assert moved.owner_tid == offer.b      # the pick now belongs to the other team
