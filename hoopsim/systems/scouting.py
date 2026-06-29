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

from hoopsim import config
from hoopsim.config import RATING_MAX

# Runtime override of config.FOG_OF_WAR. ``None`` defers to the config default; set via
# :func:`set_fog` so the user can flip fog off to inspect raw ceilings and back on for play.
_FOG_OVERRIDE = None


def fog_enabled() -> bool:
    return config.FOG_OF_WAR if _FOG_OVERRIDE is None else _FOG_OVERRIDE


def set_fog(enabled) -> None:
    """Turn fog on/off at runtime; pass ``None`` to fall back to the config default."""
    global _FOG_OVERRIDE
    _FOG_OVERRIDE = enabled

# Half-width of the potential band by how established a player is. Prospects are the foggiest;
# once a player has a few pro seasons under his belt his ceiling is essentially known.
_UNC_PROSPECT = 7
_UNC_ROOKIE = 5
_UNC_SOPHOMORE = 3
_UNC_KNOWN = 1

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


def pot_uncertainty(player) -> int:
    """Half-width of the potential band: wide for prospects, tight for veterans."""
    if player.age >= 27 or player.experience >= 4:
        return _UNC_KNOWN
    if player.experience >= 2:
        return _UNC_SOPHOMORE
    if player.experience >= 1:
        return _UNC_ROOKIE
    return _UNC_PROSPECT


def potential_grade(value: int) -> str:
    for cut, letter in _GRADE_CUTS:
        if value >= cut:
            return letter
    return "D"


def pot_view(player) -> PotentialView:
    """Fogged potential for display: a band + grade, with the raw number only once it's settled.

    With fog disabled the band collapses to the exact ceiling so the raw numbers are visible.
    """
    est = player.scouted_potential()
    if not fog_enabled():
        return PotentialView(grade=potential_grade(est), low=est, high=est, known=True, value=est)
    unc = pot_uncertainty(player)
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


def pot_band_str(player) -> str:
    """Compact human string: ``"82"`` when known, else a banded ``"78–86"``."""
    v = pot_view(player)
    if v.known or v.low == v.high:
        return str(v.value)
    return f"{v.low}–{v.high}"


def pot_display(player) -> str:
    """Grade + band, e.g. ``"A- (81–87)"`` or ``"B (78)"`` for a settled veteran."""
    v = pot_view(player)
    return f"{v.grade} ({pot_band_str(player)})"
