"""Synthetic history fabricated at world creation, so a brand-new league isn't a blank slate.

Without this, season one starts with veterans who have no past — empty career pages, an empty
Hall of Fame, and "all-time" records that mean nothing until a dozen seasons have been simmed. This
module backfills two cohorts into the shared career ledger (see ``systems/legacy.py``):

1. **Living veterans** — every rostered/free-agent pro with pro experience gets a fabricated
   per-season career arc (rise → peak → today's rating), accolades consistent with that peak, and a
   draft slot. The arc length matches ``experience`` so aging/salary logic stays coherent.
2. **Retired legends** — a cohort of all-time greats who never played a live game, written straight
   into the Hall of Fame and the record book so legends and records exist from tip-off.

Everything draws from a **dedicated rng** seeded off the world seed, applied *after* the roster is
built. The world's own rng is never touched, so every seed reproduces the exact same league — the
backstory is layered on top, identical to how coaches are assigned.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from hoopsim.gen.namegen import NameGenerator
from hoopsim.gen.playergen import make_player
from hoopsim.models.player import Player
from hoopsim.models.world import World
from hoopsim.rng import Rng
from hoopsim.systems import legacy

BACKSTORY_SALT = 0xBACC5704
NUM_LEGENDS = 30
PEAK_AGE = 27


def apply_backstory(world: World, seed: int) -> None:
    """Fabricate veteran histories and a retired-legends cohort. Uses a separate rng stream."""
    rng = Rng(seed ^ BACKSTORY_SALT)
    names = NameGenerator(rng)
    team_abbrevs = [t.abbrev for t in world.team_list()]
    for p in world.players.values():
        if p.class_year == 0 and p.experience > 0 and not p.career:
            _fabricate(p, world, rng, team_abbrevs)
    _generate_legends(world, rng, names, team_abbrevs, NUM_LEGENDS)


# ---------------------------------------------------------------------------
# Career-arc fabrication
# ---------------------------------------------------------------------------
def _career_arc(rng: Rng, *, years: int, peak: int, finish: int, position: str,
                team: str, last_year: int, entry_age: int) -> Tuple[List[dict], Dict[str, int]]:
    """A believable ``years``-long career: ovr rises toward ``peak`` around age 27, then declines.

    The arc is anchored at both ends — it starts at a rookie level and the most recent season lands
    on ``finish`` (the player's current rating, or a legend's rating at retirement). Returns
    (per-season lines, accolade tally)."""
    big = position in ("PF", "C")
    guard = position in ("PG", "SG")
    start_year = last_year - years + 1
    last_age = entry_age + years - 1
    rookie = max(50, min(finish, peak) - rng.randint(8, 18))
    career: List[dict] = []
    accolades: Dict[str, int] = {}
    for i in range(years):
        age = entry_age + i
        if i == years - 1:
            ovr = finish                                       # anchor the latest season to "now"
        elif last_age <= PEAK_AGE:                             # still on the way up — rise to finish
            t = (age - entry_age) / max(1, last_age - entry_age)
            ovr = rookie + (finish - rookie) * t
        elif age <= PEAK_AGE:                                  # rise from rookie to the peak
            t = (age - entry_age) / max(1, PEAK_AGE - entry_age)
            ovr = rookie + (peak - rookie) * t
        else:                                                  # decline from peak toward finish
            t = (age - PEAK_AGE) / max(1, last_age - PEAK_AGE)
            ovr = peak - (peak - finish) * t
        ovr = int(max(50, min(99, round(ovr + (0 if i == years - 1 else rng.gauss(0, 1.5))))))
        base = max(0, ovr - 55)
        ppg = round(max(1.0, 2 + base * 0.62 + rng.gauss(0, 1.2)), 1)
        rpg = round(max(0.5, 2 + base * (0.5 if big else 0.16) + rng.gauss(0, 0.5)), 1)
        apg = round(max(0.4, 1 + base * (0.42 if guard else 0.10) + rng.gauss(0, 0.4)), 1)
        career.append({"year": start_year + i, "team": team, "gp": rng.randint(58, 80),
                       "ppg": ppg, "rpg": rpg, "apg": apg, "ovr": ovr})
        if ovr >= 86 and rng.chance(0.7):
            accolades["all_league"] = accolades.get("all_league", 0) + 1
        if ovr >= 93 and rng.chance(0.55):
            accolades["mvp"] = accolades.get("mvp", 0) + 1
        if big and ovr >= 88 and rng.chance(0.25):
            accolades["dpoy"] = accolades.get("dpoy", 0) + 1
        if ppg >= 27 and rng.chance(0.35):
            accolades["scoring_title"] = accolades.get("scoring_title", 0) + 1
    if rookie >= 72 and rng.chance(0.12):
        accolades["roy"] = 1
    rings = sum(1 for _ in range(years) if rng.chance(0.05 + max(0, peak - 85) * 0.012))
    if rings:
        accolades["champion"] = rings
    return career, accolades


def _draft_slot(rng: Rng, n_teams: int, team_abbrevs: List[str], peak: int,
                entry_year: int) -> Optional[dict]:
    """A plausible draft slot from peak talent — stars go early, fringe vets may go undrafted."""
    if peak < 66 and rng.chance(0.6):
        return None
    base = int(round((99 - peak) * 2.0)) + rng.randint(-4, 7)
    pick = max(1, min(2 * n_teams, base))
    return {
        "year": entry_year,
        "round": 1 if pick <= n_teams else 2,
        "pick": pick,
        "team": rng.choice(team_abbrevs),
    }


def _fabricate(p: Player, world: World, rng: Rng, team_abbrevs: List[str]) -> None:
    """Give a living veteran a fabricated career arc, accolades, and draft slot."""
    years = p.experience
    cur = p.overall
    # Older-and-still-good ⇒ higher inferred peak (they've declined further from it).
    peak = min(99, max(cur, cur + rng.randint(0, max(0, p.age - PEAK_AGE)) + rng.randint(0, 4)))
    team = world.teams[p.team_id].abbrev if p.team_id in world.teams else rng.choice(team_abbrevs)
    entry_age = max(19, p.age - years)
    career, accolades = _career_arc(rng, years=years, peak=peak, finish=cur, position=p.position,
                                    team=team, last_year=world.season_year - 1, entry_age=entry_age)
    p.career = career
    p.accolades = accolades
    entry_year = world.season_year - years
    p.draft = _draft_slot(rng, len(world.teams), team_abbrevs, peak, entry_year)


# ---------------------------------------------------------------------------
# Retired legends → Hall of Fame & record book
# ---------------------------------------------------------------------------
def _generate_legends(world: World, rng: Rng, names: NameGenerator,
                      team_abbrevs: List[str], n: int) -> None:
    """Create retired all-time greats as self-contained résumé snapshots (never rostered)."""
    for _ in range(n):
        peak = rng.randint(86, 99)
        years = rng.randint(12, 20)
        finish = max(60, peak - rng.randint(8, 16))
        retired_year = world.season_year - rng.randint(1, 18)
        # A throwaway Player lets us reuse legacy.resume() for a consistent snapshot shape.
        p = make_player(rng, world.new_pid(), names, target_overall=finish,
                        age=PEAK_AGE + (world.season_year - retired_year) + rng.randint(2, 6))
        p.experience = years
        team = rng.choice(team_abbrevs)
        p.career, p.accolades = _career_arc(rng, years=years, peak=peak, finish=finish,
                                            position=p.position, team=team, last_year=retired_year,
                                            entry_age=19 + rng.randint(0, 2))
        p.draft = _draft_slot(rng, len(world.teams), team_abbrevs, peak,
                              retired_year - years + 1)
        snap = legacy.resume(world, p, retired_year=retired_year)
        world.retired.append(snap)
        if snap["hof"]:
            world.hall_of_fame.append(snap)
