# 🏀 HoopR

A text-based, *Football-Manager-style* basketball management simulation that runs in your
terminal. Take over an NBA franchise, set tactics, watch possession-by-possession games unfold
in play-by-play, wheel and deal on the trade market, sign free agents under the salary cap,
draft and develop prospects, and chase a championship across multiple seasons.

Built on a procedurally generated league (fictional teams and players), a deterministic,
seedable simulation core, and a rich terminal UI.

```
  _   _  ___   ___  ___ ___
 | | | |/ _ \ / _ \| _ \ _ \
 | |_| | (_) | (_) |  _/   /
  \___/ \___/ \___/|_| |_|_\
```

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m hoopr
```

> Requires Python 3.9+. The only runtime dependency is [`rich`](https://github.com/Textualize/rich).

From the main menu: **New Career → choose your league (NBA or College) → pick your team**, and
you're in charge.

## Game modes

At the start of a career you choose which league to manage. Both leagues coexist in one world and
are connected by the **draft pipeline**.

- **🏀 NBA franchise** — salary cap, trades, free agency, an 82-game (or Quick 30) season,
  play-in, best-of-7 playoffs, and a lottery draft.
- **🎓 College program** — pick from 32 programs across four conferences and a **college economy
  chosen at game start**:
  - **Scholarship mode** — a traditional 13-scholarship limit and allocation; recruit on prestige
    and active interest.
  - **NIL mode** — manage an NIL collective budget, sign players to NIL deals, watch brand value
    grow, and recruit with NIL money and marketability.

  A college season runs through conference standings, single-elimination **conference
  tournaments**, and a seeded **national tournament**. In the offseason your players develop,
  declare for (or graduate into) the **NBA Draft**, and you recruit the next class.

## What you can do

- **Manage a roster** — view detailed player cards (ratings grouped by Physical / Offense /
  Defense / Mental), depth, contracts, and injuries.
- **Set tactics** — pace, offensive focus, ball movement, defensive scheme, defensive pressure,
  and rebounding. Tactics genuinely shift outcomes in the engine.
- **Play possession-by-possession games** — watch a streaming play-by-play with a running score,
  or quick-sim. Every game produces a full, reconciled box score.
- **Run a season** — an 82-game (or Quick 30-game) schedule, live standings with tiebreakers,
  play-in tournament, and a best-of-7 playoff bracket through to a champion.
- **Work the front office** — propose cap-legal trades (with an AI that values players by
  production, age, upside, and contract), sign free agents within the salary cap, and track
  finances and the luxury tax.
- **Draft & develop** — a lottery-weighted, two-round draft (interactive for your picks), rookie
  scale contracts, and an offseason where young players grow toward their potential while
  veterans decline.
- **Save & load** — multiple named save slots plus autosave, with fully reproducible simulations
  (the RNG state is part of the save).

## How a season flows

```
Preseason → Regular Season → Play-In → Playoffs → Draft → Free Agency → Offseason → (next year)
```

You advance at your own pace: watch or quick-sim your next game, simulate a week, then handle the
postseason and offseason when they arrive.

## Project layout

```
hoopr/
  config.py          # all tunables (cap numbers, ratings scale, pace, injury rates…)
  rng.py             # seedable, save-restorable RNG
  models/            # pure data: player, team, contract, tactics, league, draft, world
  gen/               # procedural generation: names, players, NBA league, college world
  sim/               # engine (possessions + PBP), ratings, boxscore, season, playoffs,
                     #   college_tourney (single-elim conference + national tournaments)
  systems/           # cap, trades, free agency, draft, development, offseason
                     #   + college: recruiting, collegefin (scholarship/NIL), college_offseason
  save/              # JSON serialization (schema-versioned) + save slots
  ui/                # rich terminal UI: console, theme, widgets, screens, college_ui
  data/              # team, college, and name pools (JSON)
tests/               # pytest suite (engine, season, cap/trades, draft, save…)
```

**Design principle:** strict layering — `models` (data) ← `sim`/`systems` (logic) ← `ui`
(rendering). Game logic never imports `rich`; the UI never holds game logic. This keeps the core
testable and a future web UI a drop-in front-end.

## Running the tests

```bash
pytest -q
```

The suite covers box-score reconciliation, realistic stat distributions, schedule/standings
correctness, cap legality, trade validation, draft/development, and byte-identical save
round-trips with reproducible RNG.

## Roadmap

Implemented today: the **NBA franchise** experience, the **College** experience with both the
**Scholarship** and **NIL** economies (chosen at game start), and the **college → NBA draft
pipeline** connecting them.

Still on the roadmap:

- **International prospects** entering via the NBA draft and recruitable to college programs.
- **Transfer portal** for college rosters.
- **Advanced NBA cap** rules (apron, sign-and-trade), two-way / G-League contracts.
- **Deeper scouting**, awards / Hall of Fame / history, chemistry and momentum, coaching staff.
- A richer **NIL marketplace** (negotiated endorsement packages, brand events).

## Notes

- Teams and players are entirely fictional and procedurally generated.
- A league is created from a random seed shown when you start a career; the same seed reproduces
  the same league.
