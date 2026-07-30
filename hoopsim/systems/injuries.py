"""Between-game injury risk, conditioning load, and rest.

The engine already rolls for dramatic in-game injuries possession by possession
(``sim/engine.py``). This module owns everything that happens *between* games: how a player's
``condition`` drains under minutes and recovers on light nights, the wear-and-tear injury a
heavy workload produces, and the elevated risk a player carries for a while after coming back.

The point of the design is that ``durability`` should be a rating you can feel. A fragile big
who plays 38 minutes a night on a worn-down body gets hurt, misses time, comes back at elevated
risk, and gets hurt again — the pattern real "injury prone" players have. A durable one absorbs
the same workload. Nothing here touches shot-making: in-game fatigue already does that, and
stacking a second performance penalty on top would double-dip against the tuned shot math.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from hoopsim.config import BASE_INJURY_RATE
from hoopsim.models import staff
from hoopsim.models.player import Injury, Player
from hoopsim.models.team import Team, roster_players
from hoopsim.models.world import World

# -- conditioning -----------------------------------------------------------
# Recovery is proportional to how depleted a player already is, not a flat nightly amount. That
# matters because every team plays every day: with flat recovery, any workload under the break-even
# point pins at 100 and anything over it slides to the floor, so condition ends up binary. A
# restoring force instead gives each workload its own equilibrium — roughly 76 for a 38-minute
# star, 82 for a 30-minute starter, 94 for a bench player — and one night off recovers most of it.
CONDITION_DRAIN_PER_MIN = 0.55
CONDITION_RECOVERY_RATE = 0.4      # share of the deficit regained per night
CONDITION_RECOVERY_BASE = 1.5
CONDITION_FLOOR = 25.0

# -- injury risk ------------------------------------------------------------
# Multipliers on BASE_INJURY_RATE (0.012/game, so roughly one injury per player-season at
# baseline). Each factor is centered on 1.0 for a league-average player so the league-wide
# injury rate stays near that baseline and only the *distribution* shifts onto fragile,
# overworked, and older players.
RATING_PIVOT = 70              # the 70-anchor convention used everywhere in this repo
DURABILITY_SCALE = 0.025       # per point of durability below/above the pivot; a 50-durability
                               # player carries ~3x the risk of a 90, which is the whole point
CONDITION_PIVOT = 85.0
CONDITION_SCALE = 0.012        # per point of condition below the pivot
AGE_PIVOT = 28
AGE_SCALE = 0.05               # per year past the pivot
HEAVY_MINUTES = 34.0
MINUTES_SCALE = 0.03           # per minute past HEAVY_MINUTES in the game just played
RTP_MULTIPLIER = 2.4           # re-injury risk while inside the return-to-play window
MAX_RISK = 0.20                # hard ceiling so no single game becomes a coin flip

# -- staff effects ----------------------------------------------------------
# Per level of the relevant specialist (1-5). Capped well below 1.0 so a full elite staff shifts
# the odds meaningfully without making a team injury-proof — an elite trainer is worth about a
# third of the risk, not all of it.
TRAINER_RISK_REDUCTION = 0.07      # Athletic Trainer: fewer wear-and-tear injuries
CONDITIONING_RECOVERY_BONUS = 0.06  # Strength & Conditioning: better nightly recovery

# Return-to-play window by severity: how many games a returning player stays fragile.
RTP_GAMES = {"minor": 2, "moderate": 6, "major": 14}

# A player needs a fieldable rotation; rest requests that would breach this are overridden.
MIN_AVAILABLE = 8

# Injury flavor: (body part, description, min games, max games). The length range belongs to the
# specific ailment rather than the severity band, because "torn ACL — out 15 games" reads as
# broken no matter how well the numbers balance. Descriptions are all countable singular nouns so
# they survive being dropped into "is out with a {description}".
_AILMENTS: Dict[str, List[tuple]] = {
    "minor": [
        ("ankle", "sprained ankle", 2, 5), ("knee", "sore knee", 1, 3),
        ("back", "back strain", 2, 4), ("hand", "jammed finger", 1, 3),
        ("hip", "hip pointer", 1, 4), ("shoulder", "shoulder contusion", 1, 3),
        ("quad", "quad contusion", 1, 3), ("foot", "sore foot", 1, 3),
    ],
    "moderate": [
        ("hamstring", "strained hamstring", 6, 14), ("groin", "groin strain", 5, 12),
        ("knee", "sprained MCL", 8, 18), ("ankle", "high ankle sprain", 6, 15),
        ("calf", "calf strain", 5, 12), ("shoulder", "shoulder strain", 4, 10),
        ("wrist", "wrist sprain", 4, 10), ("rib", "rib contusion", 3, 8),
    ],
    "major": [
        ("knee", "torn ACL", 60, 82), ("achilles", "ruptured Achilles", 65, 82),
        ("foot", "fractured foot", 25, 45), ("back", "herniated disc", 22, 40),
        ("knee", "torn meniscus", 18, 35), ("hand", "fractured hand", 15, 28),
        ("shoulder", "torn labrum", 30, 50), ("leg", "stress fracture", 20, 38),
    ],
}


# ---------------------------------------------------------------------------
# Conditioning
# ---------------------------------------------------------------------------
def _stamina_factor(player: Player) -> float:
    """Higher stamina drains slower and recovers faster (1.0 at the 70 anchor)."""
    return 1.0 + (RATING_PIVOT - player.ratings["stamina"]) * 0.006


def update_condition(player: Player, minutes: float, conditioning_level: int = 0) -> None:
    """Apply one game's load, then a night of recovery.

    ``conditioning_level`` is the team's Strength & Conditioning grade (0 = nobody on staff).
    """
    if minutes > 0:
        player.condition -= minutes * CONDITION_DRAIN_PER_MIN * _stamina_factor(player)
    deficit = max(0.0, 100.0 - player.condition)
    rate = CONDITION_RECOVERY_RATE + conditioning_level * CONDITIONING_RECOVERY_BONUS
    recovery = (CONDITION_RECOVERY_BASE + deficit * rate)
    recovery /= max(0.6, _stamina_factor(player))
    if player.is_injured or player.resting:
        recovery *= 1.25                      # sitting is how you actually get it back
    player.condition = max(CONDITION_FLOOR, min(100.0, player.condition + recovery))


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------
def injury_risk(player: Player, minutes: float, trainer_level: int = 0) -> float:
    """Per-game probability this player picks up a wear-and-tear injury.

    ``trainer_level`` is the team's Athletic Trainer grade (0 = no trainer on staff).
    """
    if minutes <= 0:
        return 0.0
    risk = BASE_INJURY_RATE * (1.0 - trainer_level * TRAINER_RISK_REDUCTION)
    risk *= max(0.25, 1.0 + (RATING_PIVOT - player.ratings["durability"]) * DURABILITY_SCALE)
    risk *= max(1.0, 1.0 + (CONDITION_PIVOT - player.condition) * CONDITION_SCALE)
    risk *= max(1.0, 1.0 + (player.age - AGE_PIVOT) * AGE_SCALE)
    risk *= max(1.0, 1.0 + (minutes - HEAVY_MINUTES) * MINUTES_SCALE)
    if player.rtp_games > 0:
        risk *= RTP_MULTIPLIER
    return min(MAX_RISK, risk)


def _roll_severity(rng, player: Player) -> str:
    """Pick a severity. A player still inside his return-to-play window skews worse."""
    roll = rng.random()
    if player.rtp_games > 0:
        # Skew toward the serious end for a re-injury. Note the direction: the bands below run
        # minor-first, so making a re-injury worse means pushing the roll UP, not down.
        roll = roll ** 0.6
    if roll < 0.72:
        return "minor"
    if roll < 0.98:
        return "moderate"
    # Season-enders are genuinely rare — a couple of torn ACLs a year across the whole league,
    # not one a week. Keep this tail thin or the injury report stops being believable.
    return "major"


def make_injury(rng, severity: str, games: Optional[int] = None) -> Injury:
    """Build an injury with flavor appropriate to its severity.

    ``games`` is normally left to the ailment's own range. The engine's in-game roll passes a
    length it already picked; that length is honored, but clamped into the chosen ailment's range
    so a torn ACL can never come back as a two-week absence.
    """
    body_part, description, lo, hi = rng.choice(_AILMENTS[severity])
    games = rng.randint(lo, hi) if games is None else max(lo, min(hi, games))
    return Injury(description=description, games_remaining=games, severity=severity,
                  body_part=body_part, games_total=games)


def record_injury(world: World, player: Player, injury: Injury) -> None:
    """Attach an injury and log it to the player's permanent history.

    A worse injury supersedes a lighter one already in progress; a lighter one never shortens
    an existing recovery.
    """
    if player.injury is not None and injury.games_remaining <= player.injury.games_remaining:
        return
    player.injury = injury
    player.resting = False                    # an injury overrides a rest request
    player.injury_history.append({
        "year": world.season_year,
        "description": injury.description,
        "body_part": injury.body_part,
        "severity": injury.severity,
        "games": injury.games_remaining,
    })


def check_wear_and_tear(world: World, player: Player, minutes: float,
                        trainer_level: int = 0) -> Optional[Injury]:
    """Roll the between-game injury check for one player. Returns the injury, if any."""
    if player.is_injured or minutes <= 0:
        return None
    if not world.rng.chance(injury_risk(player, minutes, trainer_level)):
        return None
    severity = _roll_severity(world.rng, player)
    injury = make_injury(world.rng, severity)
    record_injury(world, player, injury)
    return injury


# ---------------------------------------------------------------------------
# Post-game hook (called once per team per game from sim/season.py)
# ---------------------------------------------------------------------------
def post_game(world: World, team: Team, minutes_by_pid: Dict[int, float]) -> List[tuple]:
    """Update condition and roll wear-and-tear for everyone on a roster after a game.

    Returns ``(player, injury)`` pairs for anything new, so callers can report it.
    """
    trainer = staff.level_of(team.staff, "trainer")
    conditioning = staff.level_of(team.staff, "conditioning")
    new_injuries = []
    for player in roster_players(team, world.players):
        minutes = minutes_by_pid.get(player.pid, 0.0)
        update_condition(player, minutes, conditioning)
        injury = check_wear_and_tear(world, player, minutes, trainer)
        if injury is not None:
            new_injuries.append((player, injury))
    return new_injuries


def heal_one(player: Player) -> bool:
    """Tick one game off an injury. Returns True if the player just came back.

    Clearing an injury opens a return-to-play window sized by how bad it was — that window is
    what makes a serious injury echo forward instead of vanishing on the day he is cleared.
    """
    if player.injury is None:
        return False
    player.injury.games_remaining -= 1
    player.games_missed += 1
    if player.injury.games_remaining > 0:
        return False
    player.rtp_games = RTP_GAMES.get(player.injury.severity, 2)
    player.injury = None
    return True


def tick_rtp(player: Player) -> None:
    """Burn down the return-to-play window on a day the player was healthy."""
    if player.rtp_games > 0 and not player.is_injured:
        player.rtp_games -= 1


# ---------------------------------------------------------------------------
# Rest
# ---------------------------------------------------------------------------
def resolve_rest(team: Team, players: Dict[int, Player]) -> List[Player]:
    """Clear rest flags that would leave a team without a fieldable rotation.

    Rest is advisory: the user can flag anyone, but a roster gutted by injuries plays its
    healthy bodies regardless. Returns the players forced back into action.
    """
    healthy = [p for p in roster_players(team, players) if not p.is_injured]
    resting = [p for p in healthy if p.resting]
    shortfall = MIN_AVAILABLE - (len(healthy) - len(resting))
    if shortfall <= 0:
        return []
    resting.sort(key=lambda p: p.overall, reverse=True)
    forced = resting[:shortfall]
    for player in forced:
        player.resting = False
    return forced


def clear_rest(team: Team, players: Dict[int, Player]) -> None:
    """Drop every rest flag on a roster (used at season boundaries)."""
    for player in roster_players(team, players):
        player.resting = False
