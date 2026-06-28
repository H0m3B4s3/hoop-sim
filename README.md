# 🏀 HoopSim

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
python -m hoopsim
```

> Requires Python 3.9+. The only runtime dependency is [`rich`](https://github.com/Textualize/rich).

From the main menu: **New Career → choose your league (NBA or College) → pick your team**, and
you're in charge.

## Game modes

At the start of a career you choose which league to manage. Both leagues coexist in one world and
are connected by the **draft pipeline**.

- **🏀 NBA franchise** — a salary cap that **grows each year**, trades, free agency,
  **re-signing and extending** your own players (Bird rights), **dead-cap penalties** when you
  waive guaranteed contracts, an 82-game (or Quick 30) season, play-in, best-of-7 playoffs, and a
  lottery draft. AI teams now **re-sign their own keepers** before free agency opens, so only the
  players a team chooses to let walk reach the market.
- **🎓 College program** — pick from **64 programs across eight conferences** spanning power,
  mid-major, and low-major prestige tiers, with a **college economy chosen at game start**:
  - **Scholarship mode** — a traditional 13-scholarship limit and allocation; recruit on prestige
    and active interest.
  - **NIL mode** — manage an NIL collective budget, sign players to NIL deals, watch brand value
    grow, and recruit with NIL money and marketability.

  College games are played in **two 20-minute halves** at a slower, college pace. A season runs
  through conference standings, single-elimination **conference tournaments**, and a seeded
  32-team **national tournament**. In the offseason your players develop, declare for (or graduate
  into) the **NBA Draft**, and you recruit the next class.

In both modes you can **set and lock your own starting five** (positions are flexible — a guard
will slot up to the point if that's your best five), and close games feature **clutch lineups and
late-game intentional fouling**.

## What you can do

- **Manage a roster** — view detailed player cards (ratings grouped by Physical / Offense /
  Defense / Mental), depth, contracts, and injuries.
- **Set tactics** — pace, offensive focus, ball movement, defensive scheme, defensive pressure,
  and rebounding. Tactics genuinely shift outcomes in the engine.
- **Play possession-by-possession games** — watch a streaming play-by-play with a running score,
  or quick-sim. Every game produces a full, reconciled box score.
- **Coach the finish live** — when you watch your own game, take the bench over in crunch time:
  substitutions, timeouts (a tracked resource), tempo (run / bleed clock / hold for the last shot /
  quick 3), and deliberate fouling — possession by possession. Available in the terminal and the
  web app alike (NBA & college, regular season + postseason).
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
hoopsim/
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
  web/               # FastAPI app + serializers — drives the same engine over HTTP
  data/              # team, college, and name pools (JSON)
frontend/            # React/TypeScript SPA, built into hoopsim/web/static
tools/               # dev scripts (gen_names.py regenerates data/names.json)
tests/               # pytest suite (engine, season, cap/trades, draft, save, web…)
```

**Design principle:** strict layering — `models` (data) ← `sim`/`systems` (logic) ← `ui`/`web`
(rendering). Game logic never imports `rich`; the UI never holds game logic. This kept the core
testable and let the web UI drop in as a second front-end over the same resumable engine.

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
pipeline** connecting them. Recent additions: a **league-wide scouting board** (attributes for
every player, sortable/filterable), a **trade block** that surfaces the aging veterans
non-contenders are shopping, an **NBA trade deadline** (~⅔ through the season; waivers stay open
after), **player attributes inside the trade screen**, **soliciting trade offers** (shop your own
players around the league and accept the best cap-legal package interested teams offer),
**tradeable future draft picks** (a rolling multi-year window of first- and second-rounders that
move in trades, are valued by the original team's outlook, and are honored at draft time — "via"
ownership and all), **coach-mode end-game instructions** (per-team crunch-time tactics the engine
applies: foul-when-trailing aggressiveness, foul-up-3 to deny a tying triple resolved by an
IQ-vs-IQ roll, and whether to ride your closers or keep the rotation), a **deeper play-by-play**
that now surfaces missed shots, rebounds, blocks, and assists, and a polished **playoff bracket**
in the web app with full regular-season → postseason progression, and a **trade block + AI-initiated
offers** (mark players available and rival GMs bring you cap-legal packages — players and/or picks —
as you sim, surfaced in a non-blocking Offers inbox with a nav badge; offers are capped, expire after
a week, and clear at the deadline), and **end-of-season awards & league history** (MVP, Rookie of the
Year, Defensive POY, Most Improved, All-League first/second/third teams, and statistical leaders —
crowned each offseason and browsable in a History tab alongside past champions).

Latest — **roster-building realism**: waiving a guaranteed, above-minimum contract now leaves
**dead money** on your cap, stretched across future seasons (minimum deals stay free to cut), shown
in the waive confirm and the Finances panel; **AI teams re-sign their own keepers** (stars, rising
youth, and rotation-caliber players, via Bird rights) before free agency, so the market is no longer
flooded with talent every team would obviously keep; the **lineup screen now shows potential, an
offense/defense read, and projected minutes** so you can prioritize upside without bouncing to the
roster page; and **live crunch-time subs surface each player's offense/defense and key skills** to
inform who you put on the floor for the next possession.

The web app now runs a **full college career** end to end — regular season, single-elim conference
and national tournaments (with live coaching), and the offseason: the NBA draft pipeline (your
declared players drafted by the background NBA) and **recruiting** (NIL bidding or scholarship
offers on a board, resolved on Signing Day) before rolling into the next season. NBA and college
reach parity in the browser.

**Live crunch-time coaching**: when you watch your own game you can take the bench over
possession-by-possession in the closing window — substitutions, timeouts (a tracked resource),
tempo (run / bleed clock / hold for the last shot / quick 3), and deliberate fouling. The game
engine is a resumable generator, so the terminal blocks on your input while the web app drives the
very same simulation across HTTP requests; it runs in the terminal and the web app alike (NBA &
college, regular season + postseason).

Still on the roadmap:

- **International prospects** entering via the NBA draft and recruitable to college programs.
- **Transfer portal** for college rosters.
- **Advanced NBA cap** rules (apron, sign-and-trade), two-way / G-League contracts.
- **Deeper scouting**, Hall of Fame / career milestones, chemistry and momentum, coaching staff.
- A richer **NIL marketplace** (negotiated endorsement packages, brand events).

### Future work (not started)

Trades & draft assets
- **Pick protections & swaps** (conditional picks, top-N protections rolling to the next year).

Coach mode — end-of-game situations (NBA & CBB)
- **Interactive crunch-time coaching is built** across the terminal and web app (NBA & college,
  regular season + postseason — including the college tournament in the browser).

Tiered signing — free agency & recruiting (next up)
- Today both markets resolve in a single instant pass ([`run_free_agency`](hoopsim/systems/freeagency.py),
  [`resolve_recruiting`](hoopsim/systems/recruiting.py)), which makes them feel one-and-done.
- **Rounds of free agency**: top-tier (max-contract) FAs resolve first; pursue a primary target, and
  if he signs elsewhere that tier comes off the board, the remaining pool re-prices downward, and you
  work the next group — with a decision point between waves.
- **Phased recruiting** for both scholarship and NIL: five-star prospects commit first, and missing an
  initial target leaves recruits in the pool so you can work down the board instead of losing them.

Rotations & depth chart (planned)
- The depth chart is **display-only** today; the engine fills five on-court spots by a flat best-5
  priority from `team.minutes_target`, with no position slots during play
  ([`choose_lineup`](hoopsim/sim/engine.py)).
- **Position-aware depth**: a per-position depth order the substitution engine respects, so your
  second-string PG actually replaces the PG and the floor stays balanced (configurable next-man-up
  rules — SG slides to PG, PF to C).
- **Role tags** — `sixth_man`, `defensive_ace`, `closer` — that bias the rotation math: a closer
  overrides crunch-time selection, a defensive ace earns minutes against strong offenses, and a sixth
  man jumps the bench queue.

## Notes

- Teams and players are entirely fictional and procedurally generated.
- A league is created from a random seed shown when you start a career; the same seed reproduces
  the same league.
