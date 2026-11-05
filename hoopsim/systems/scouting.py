"""Fog of war over player potential.

The engine knows a player's exact ``potential``; the *user* shouldn't. A prospect's ceiling is
a guess, and the guess gets sharper the more pro basketball we've watched him play. This module
turns the hidden number into what a front office would actually have: a confidence band and a
coarse letter grade, with the uncertainty shrinking as a player establishes himself.

Internals (AI valuations, the draft board sort) keep using :meth:`Player.scouted_potential`; only
*display* should route through here so we never print the raw ceiling for an unproven player.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from hoopsim import config
from hoopsim.config import RATING_MAX


def fog_enabled(world=None) -> bool:
    """Whether this career hides exact ceilings. Each career carries its own setting
    (``world.fog_of_war``; ``None`` means the config default), so one player flipping fog off on a
    shared server never changes what anyone else sees."""
    setting = getattr(world, "fog_of_war", None)
    return config.FOG_OF_WAR if setting is None else setting

# Half-width of the potential band by how established a player is. Prospects are the foggiest;
# once a player has a few pro seasons under his belt his ceiling is essentially known.
_UNC_PROSPECT = 7
_UNC_ROOKIE = 5
_UNC_SOPHOMORE = 3
_UNC_KNOWN = 1

# Band narrowing per level of a Head Scout (1-5), floored at _UNC_KNOWN so even the best scout
# in the league still leaves a sliver of doubt on an unproven prospect.
SCOUT_BAND_NARROWING = 0.12

# Letter grade cut points on the (scouted) potential scale. Coarse on purpose — a grade leaks
# far less than a precise integer.
_GRADE_CUTS = [
    (90, "A+"), (86, "A"), (83, "A-"),
    (80, "B+"), (77, "B"), (74, "B-"),
    (71, "C+"), (68, "C"), (64, "C-"),
    (0, "D"),
]


@dataclass
class PotentialView:
    grade: str          # coarse letter grade (always safe to show)
    low: int            # bottom of the confidence band
    high: int           # top of the confidence band
    known: bool         # True once the ceiling is essentially settled
    value: int          # point estimate — only meaningful/shown when ``known``


def pot_uncertainty(player, scout_level: int = 0) -> int:
    """Half-width of the potential band: wide for prospects, tight for veterans.

    ``scout_level`` is the viewing team's Head Scout grade (0 = nobody on staff). A good scout
    narrows the band — you see a tighter read on the same prospect — but never collapses it to
    certainty, so the last of the guesswork always stays yours.
    """
    if player.age >= 27 or player.experience >= 4:
        base = _UNC_KNOWN
    elif player.experience >= 2:
        base = _UNC_SOPHOMORE
    elif player.experience >= 1:
        base = _UNC_ROOKIE
    else:
        base = _UNC_PROSPECT
    if scout_level:
        base = max(_UNC_KNOWN, int(round(base * (1.0 - scout_level * SCOUT_BAND_NARROWING))))
    return base


def potential_grade(value: int) -> str:
    for cut, letter in _GRADE_CUTS:
        if value >= cut:
            return letter
    return "D"


def pot_view(player, scout_level: int = 0, fog: Optional[bool] = None) -> PotentialView:
    """Fogged potential for display: a band + grade, with the raw number only once it's settled.

    With fog disabled the band collapses to the exact ceiling so the raw numbers are visible.
    Pass ``fog=fog_enabled(world)`` for the viewing career; ``None`` uses the config default.
    """
    est = player.scouted_potential()
    if not (config.FOG_OF_WAR if fog is None else fog):
        return PotentialView(grade=potential_grade(est), low=est, high=est, known=True, value=est)
    unc = pot_uncertainty(player, scout_level)
    floor = player.overall
    low = max(floor, est - unc)
    high = min(RATING_MAX, est + unc)
    return PotentialView(
        grade=potential_grade(est),
        low=low,
        high=high,
        known=unc <= _UNC_KNOWN,
        value=est,
    )


def pot_band_str(player, fog: Optional[bool] = None) -> str:
    """Compact human string: ``"82"`` when known, else a banded ``"78–86"``."""
    v = pot_view(player, fog=fog)
    if v.known or v.low == v.high:
        return str(v.value)
    return f"{v.low}–{v.high}"


def pot_display(player, fog: Optional[bool] = None) -> str:
    """Grade + band, e.g. ``"A- (81–87)"`` or ``"B (78)"`` for a settled veteran."""
    v = pot_view(player, fog=fog)
    return f"{v.grade} ({pot_band_str(player, fog)})"
