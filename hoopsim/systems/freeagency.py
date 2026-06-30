"""Free-agent market: market valuation, AI signings, and a user-facing sign helper."""
from __future__ import annotations

from typing import List, Tuple

from hoopsim.config import MAX_CONTRACT_YEARS, VETERAN_MINIMUM
from hoopsim.models.contract import flat_contract
from hoopsim.models.player import Player
from hoopsim.models.team import Team, auto_set_lineup
from hoopsim.models.world import World
from hoopsim.systems import cap

TARGET_ROSTER = 14

# --- Tiered free agency ----------------------------------------------------
# Free agency resolves in waves: the top tier (max-contract caliber) opens first, and each
# subsequent wave widens the open pool to the next caliber down. Players who go unsigned as their
# tier sits on the market re-price downward each wave (the market cools), so a star nobody could
# afford in wave 0 eventually becomes a bargain. ``World.fa_wave`` is the current wave index while
# the offseason market is live, or ``None`` outside it (the in-season waiver wire, where deals are
# at full price).
FA_WAVE_THRESHOLDS = [80, 75, 70, 0]   # overall floor that opens each successive wave
FA_WAVE_NAMES = ["Max-contract targets", "Starters", "Rotation players", "Depth & minimums"]
NUM_FA_WAVES = len(FA_WAVE_THRESHOLDS)
WAVE_DISCOUNT = 0.07                    # price a still-unsigned FA cools each wave past their tier
MIN_DISCOUNT_FACTOR = 0.6              # a cooling market never drops a player below 60% of value


def natural_wave(player: Player) -> int:
    """The wave in which this player's tier first opens, by overall rating."""
    for i, floor in enumerate(FA_WAVE_THRESHOLDS):
        if player.overall >= floor:
            return i
    return NUM_FA_WAVES - 1


def wave_market_salary(world: World, player: Player) -> int:
    """A free agent's asking price, cooled by how long their tier has sat unsigned.

    Outside the offseason market (``world.fa_wave is None``) this is just the full market value.
    """
    base = cap.market_salary(player)
    if world.fa_wave is None:
        return max(VETERAN_MINIMUM, base)
    steps = max(0, world.fa_wave - natural_wave(player))
    factor = max(MIN_DISCOUNT_FACTOR, 1.0 - WAVE_DISCOUNT * steps)
    return max(VETERAN_MINIMUM, int(round(base * factor / 100_000) * 100_000))


def fa_wave_pool(world: World) -> List[Player]:
    """Free agents whose tier has opened in the current wave (highest overall first)."""
    wave = world.fa_wave if world.fa_wave is not None else NUM_FA_WAVES - 1
    pool = [p for p in world.free_agent_players() if natural_wave(p) <= wave]
    return sorted(pool, key=lambda p: p.overall, reverse=True)


def start_fa_market(world: World) -> None:
    """Open the tiered offseason free-agent market at the top wave."""
    world.fa_wave = 0


def end_fa_market(world: World) -> None:
    """Close the offseason market; later signings (waivers) are at full price again."""
    world.fa_wave = None


def advance_fa_wave(world: World) -> bool:
    """Move to the next wave. Returns ``True`` if a wave remains, ``False`` once the board clears."""
    if world.fa_wave is None:
        return False
    world.fa_wave += 1
    if world.fa_wave >= NUM_FA_WAVES:
        end_fa_market(world)
        return False
    return True


def contract_years_for(player: Player) -> int:
    """The contract length a free agent prefers (younger players bet on themselves, vets want
    security on shorter deals)."""
    if player.age < 30:
        return 3
    if player.age < 33:
        return 2
    return 1


def _quality(player: Player) -> float:
    """How much leverage a free agent has, 0 (fringe/minimum) .. 1 (max-contract star)."""
    return max(0.0, min(1.0, (player.overall - 65) / 25.0))


def required_salary(world: World, player: Player, years: int) -> int:
    """The salary it takes to sign this free agent *at a given contract length*.

    Term and money trade off. Offering more years than the player prefers is security they'll take
    a per-year discount for — strongly for older, lesser free agents (who crave a guaranteed job),
    barely at all for young stars. Offering fewer years than they want makes them hold out for a
    raise. At the preferred length this is just their market ask (:func:`wave_market_salary`).
    """
    target = wave_market_salary(world, player)
    pref = contract_years_for(player)
    years = max(1, min(MAX_CONTRACT_YEARS, years))
    delta = years - pref
    over_30 = max(0, player.age - 30)
    q = _quality(player)
    if delta >= 0:                                  # extra years = security → they discount
        per_year = 0.02 + 0.02 * over_30 + 0.08 * (1.0 - q)
        factor = max(0.75, 1.0 - per_year * delta)
    else:                                           # short deal → they want a premium
        per_year = 0.08 + 0.05 * over_30 + 0.06 * q
        factor = 1.0 + per_year * (-delta)
    return max(VETERAN_MINIMUM, int(round(target * factor / 100_000) * 100_000))


def offer_for(world: World, team: Team, player: Player) -> Tuple[int, int]:
    """A fair starting offer — the player's market ask at their preferred contract length.

    A free agent commands their market value; a capped-out team simply may not be able to fit it
    (that legality is enforced in :func:`sign_free_agent`). The user can negotiate term against
    money from here via :func:`required_salary`.
    """
    return wave_market_salary(world, player), contract_years_for(player)


def evaluate_offer(world: World, player: Player, salary: int, years: int) -> Tuple[bool, str]:
    """Whether the free agent accepts an offer of ``salary`` over ``years`` (willingness only —
    cap-legality is checked separately in :func:`sign_free_agent`)."""
    if years < 1 or years > MAX_CONTRACT_YEARS:
        return False, f"Contracts run 1–{MAX_CONTRACT_YEARS} years."
    req = required_salary(world, player, years)
    if salary < req:
        pref = contract_years_for(player)
        hint = "" if years >= pref else " — or offer more years for less per season"
        return False, (f"{player.short_name} wants about ${req // 1_000_000}M "
                       f"over {years}y{hint}.")
    return True, f"{player.short_name} accepts {years}y at ${salary // 1_000_000}M."


def sign_free_agent(world: World, team: Team, pid: int, salary: int, years: int
                    ) -> Tuple[bool, str]:
    """Sign a free agent after checking they accept the terms and the deal is cap-legal."""
    player = world.players[pid]
    if player.team_id is not None:
        return False, "Player is not a free agent."
    accepts, why = evaluate_offer(world, player, salary, years)
    if not accepts:
        return False, why
    ok, reason = cap.can_sign(world, team, salary)
    if not ok:
        return False, reason
    spent_mle = cap.uses_exception(world, team, salary)
    world.sign_player(pid, team.tid, flat_contract(salary, years, world.season_year))
    if spent_mle:
        team.mle_used = True
    auto_set_lineup(team, world.players)
    return True, why


def _wants_to_resign(world: World, team: Team, player: Player) -> bool:
    """Whether an AI team re-signs an expiring own player rather than letting them walk."""
    ovr = player.overall
    if player.age >= 35 and ovr < 78:
        return False                       # washed veterans walk
    if ovr >= 78:
        return True                        # keep your stars — Bird rights go over the cap
    if player.age <= 24 and player.scouted_potential() >= ovr + 4:
        return True                        # keep promising youth on the upswing
    if cap.payroll(world, team) > world.luxury_tax_line and ovr < 74:
        return False                       # tax teams shed mid-tier guys to the market
    better = sum(1 for pid in team.roster if world.players[pid].overall > ovr)
    return better < 8                      # keep rotation-caliber contributors


def run_retention(world: World) -> dict:
    """Before contracts expire, AI teams re-sign the expiring players they want to keep.

    Re-signs use Bird rights (over-the-cap), so genuine keepers stay home; only the players a
    team chooses not to retain — fringe roster filler, washed vets, the cap-squeezed — reach the
    free-agent market. The user makes their own re-sign calls, so the user team is excluded.
    """
    resigned = 0
    for team in world.team_list():
        if team.tid == world.user_team_id:
            continue
        for pid in list(team.roster):
            player = world.players[pid]
            if player.contract.years_remaining != 1:
                continue                   # only deals expiring this offseason
            if not _wants_to_resign(world, team, player):
                continue
            salary, add_years = cap.extension_offer(world, player)
            ok, _ = cap.extend_contract(world, team, pid, salary, add_years)
            if ok:
                resigned += 1
    return {"resigned": resigned}


def run_fa_wave(world: World) -> dict:
    """AI teams bid on the tier open in the current wave, within their cap. User is excluded.

    Players whose tier has not opened yet are left for a later wave; ones already passed over carry
    forward at the cooled price (:func:`wave_market_salary`).
    """
    ai_teams = [t for t in world.team_list() if t.tid != world.user_team_id]
    signings = 0
    for player in fa_wave_pool(world):
        salary = wave_market_salary(world, player)
        years = contract_years_for(player)
        candidates: List[Team] = [t for t in ai_teams if len(t.roster) < TARGET_ROSTER
                                  and cap.can_sign(world, t, salary)[0]]
        if not candidates:
            continue
        team = max(candidates, key=lambda t: cap.cap_space(world, t))
        if cap.uses_exception(world, team, salary):
            team.mle_used = True
        world.sign_player(player.pid, team.tid, flat_contract(salary, years, world.season_year))
        signings += 1
    for t in ai_teams:
        auto_set_lineup(t, world.players)
    return {"signings": signings}


def run_free_agency(world: World) -> dict:
    """Headless: AI teams work the whole tiered market, wave by wave. User is excluded."""
    start_fa_market(world)
    signings = 0
    while True:
        signings += run_fa_wave(world)["signings"]
        if not advance_fa_wave(world):
            break
    end_fa_market(world)
    return {"signings": signings}
