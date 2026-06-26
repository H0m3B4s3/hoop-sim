"""Central tunables for HoopR.

Every "magic number" that shapes the feel of the game lives here so balancing is a
single-file exercise. Salary figures are in whole dollars. Ratings are on a 25-99 scale.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Save format
# ---------------------------------------------------------------------------
SCHEMA_VERSION = 1
SAVE_DIR_NAME = "saves"          # created under the current working directory
AUTOSAVE_SLOT = "autosave"

# ---------------------------------------------------------------------------
# League shape
# ---------------------------------------------------------------------------
NUM_TEAMS = 30
CONFERENCES = ("East", "West")
TEAMS_PER_CONFERENCE = NUM_TEAMS // len(CONFERENCES)  # 15
ROSTER_MIN = 13
ROSTER_MAX = 15
STARTERS = 5
PLAYOFF_TEAMS_PER_CONF = 8        # top 6 auto, 7-10 play-in -> 2 more

# Season length presets (games per team in the regular season)
SEASON_PRESETS = {"Quick": 30, "Standard": 82}
DEFAULT_SEASON_PRESET = "Standard"

# ---------------------------------------------------------------------------
# Game (match) structure
# ---------------------------------------------------------------------------
QUARTERS = 4
QUARTER_SECONDS = 12 * 60
OT_SECONDS = 5 * 60
SHOT_CLOCK = 24

# Per-league game format: NBA plays 4x12-minute quarters; college plays 2x20-minute halves and
# at a slower pace (30-second shot clock), so possessions run longer.
GAME_FORMATS = {
    "nba": {"periods": 4, "period_seconds": 12 * 60, "label": "quarter", "abbr": "Q",
            "base_poss_seconds": 14.5},
    "college": {"periods": 2, "period_seconds": 20 * 60, "label": "half", "abbr": "H",
                "base_poss_seconds": 18.0},
}


def game_format(league: str) -> dict:
    return GAME_FORMATS.get(league, GAME_FORMATS["nba"])


def game_minutes(league: str) -> int:
    fmt = game_format(league)
    return fmt["periods"] * fmt["period_seconds"] // 60
# Average seconds a possession consumes at a neutral pace; pace tactic scales this.
BASE_SECONDS_PER_POSSESSION = 14.5
HOME_COURT_BONUS = 0.014          # added to home team's effective shooting/edge

# ---------------------------------------------------------------------------
# Ratings
# ---------------------------------------------------------------------------
RATING_MIN = 25
RATING_MAX = 99
POTENTIAL_FLOOR = 40

# ---------------------------------------------------------------------------
# Salary cap & finances (simplified, faithful in spirit; whole dollars)
# ---------------------------------------------------------------------------
SALARY_CAP = 140_000_000
LUXURY_TAX_LINE = 170_000_000
FIRST_APRON = 178_000_000
# The cap (and the tax/apron lines that track it) grow this fraction every NBA offseason as
# league revenue rises.
CAP_GROWTH_RATE = 0.035
MIN_TEAM_SALARY = int(SALARY_CAP * 0.90)
VETERAN_MINIMUM = 2_000_000
MID_LEVEL_EXCEPTION = 12_800_000
BIANNUAL_EXCEPTION = 4_500_000
MAX_CONTRACT_YEARS = 5
# Max salary tiers as a fraction of the cap, keyed by years of NBA experience.
MAX_SALARY_TIERS = ((0, 0.25), (7, 0.30), (10, 0.35))  # (min_years, cap_fraction)
# Luxury tax: dollars of tax owed per dollar over the line (flat, simplified).
LUXURY_TAX_RATE = 1.5
# Trade salary matching: outgoing salary must be within this band of incoming (over-cap).
TRADE_MATCH_FACTOR = 1.25
TRADE_MATCH_BUFFER = 250_000

# Rookie scale: first-year salary by overall draft pick index (1-based), interpolated.
ROOKIE_SCALE = {1: 12_000_000, 14: 4_000_000, 30: 2_500_000, 31: 1_100_000, 60: 1_000_000}
ROOKIE_CONTRACT_YEARS = 3

# Owner patience / budget feel — used by AI and finance screens.
DEFAULT_OWNER_BUDGET = LUXURY_TAX_LINE

# ---------------------------------------------------------------------------
# Development & aging
# ---------------------------------------------------------------------------
PEAK_AGE_LOW = 26
PEAK_AGE_HIGH = 29
ROOKIE_AGE_RANGE = (19, 23)
RETIREMENT_AGE = 38

# ---------------------------------------------------------------------------
# Injuries
# ---------------------------------------------------------------------------
# Base per-game probability a given rotation player suffers an injury, before durability.
BASE_INJURY_RATE = 0.012
# Per on-court-player, per-possession injury chance. A full-game player faces ~200 checks,
# so this is deliberately tiny (~1.5% chance of an in-game injury across a full game).
IN_GAME_INJURY_RATE = 0.00008

# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------
SEASON_START_MONTH = 10           # October
SEASON_START_DAY = 22

# ---------------------------------------------------------------------------
# College (dormant in Phase 1 — reserved so saves don't break later)
# ---------------------------------------------------------------------------
COLLEGE_ECONOMY_CHOICES = ("scholarship", "nil")
DEFAULT_COLLEGE_ECONOMY = "scholarship"
SCHOLARSHIP_LIMIT = 13
