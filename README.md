# 🏀 HoopSim

A text-based, *Football-Manager-style* basketball management simulation that runs in your
browser or your terminal. Take over an NBA franchise, set tactics, watch possession-by-possession
games unfold in play-by-play, wheel and deal on the trade market, sign free agents under the
salary cap, draft and develop prospects, and chase a championship across multiple seasons.

Built on a procedurally generated league (fictional teams and players), a deterministic,
seedable simulation core, a web app, and a rich terminal UI.

The **web app is the primary client** and gets new features first. The terminal plays the same
core game on the same engine and save format, but it has no League News, Coaching Staff, Injury
Report or advanced stats screens.

```
 _  _   ___    ___   ___  ___  ___  __  __
| || | / _ \  / _ \ | _ \/ __||_ _||  \/  |
| __ || (_) || (_) ||  _/\__ \ | | | |\/| |
|_||_| \___/  \___/ |_|  |___/|___||_|  |_|
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

### Run the web UI locally

Prefer the browser? A prebuilt frontend ships in the repo, so you only need the web extra:

```bash
pip install -e ".[web]"   # adds fastapi + uvicorn
hoopsim-web               # serves http://127.0.0.1:8000 and opens a browser
```

Only rebuild the frontend if you change anything under `frontend/` (requires Node):

```bash
cd frontend && npm install && npm run build   # outputs into hoopsim/web/static
```

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
- **Know where you stand** — **Power Rankings** (a BPI/SRS-style net rating) on every standings
  table and a dedicated tab. Each team's number blends a schedule-adjusted **Simple Rating System**
  (margin + strength of schedule) with a **roster-talent prior**; the prior carries the number early
  in the season — when records are noise — and fades as games are played. Includes a projected
  win %, so you can judge buyers vs. sellers before the trade deadline.
- **Work the front office** — propose cap-legal trades, sign free agents within the salary cap,
  and track finances and the luxury tax. The trade AI prices a star well above any pile of role
  players, pays for young upside, guards the player it's built around, and bids by where it is in
  its cycle: rebuilders prize picks and discount veterans, contenders spend picks to win now. It
  only offers deals it would accept itself, and a refusal tells you why. AI clubs trade with each
  other too: losing teams sell their veterans to contenders, busiest in the week before the
  deadline, and every deal lands on the news wire. A **front-office difficulty** (Easy / Normal /
  Hard, chosen at career start and changeable on the Finances tab) sets how hard rivals bargain in
  trades and what free agents and extension candidates ask you for; it never changes how AI teams
  deal with each other.
- **Draft & develop** — a lottery-weighted, two-round draft (interactive for your picks), rookie
  scale contracts, and an offseason where young players grow toward their potential while
  veterans decline. Each draft class has its own **shape** — most years carry only a couple of
  genuine top prospects atop a steep cliff, with the occasional loaded class that runs deep and
  the occasional down year where even the #1 pick is merely solid. Launch rosters and the draft are
  tuned to the same talent level, so the league keeps roughly 45-55 players at 80+ and a handful at
  90+ across a 20-season career instead of thinning out as the opening stars retire. Prospects show a **pre-draft
  stat line** (college/international per-game production) alongside their archetype, and you can
  **shop your picks for offers right from the draft room** — no tabbing out to the trade screen.
- **Scout under fog of war** — player **potential** is hidden behind a confidence band and a letter
  grade (e.g. `B+ (78–86)`) that tightens as a player proves himself; an unproven prospect's
  ceiling is a guess, a settled veteran's is known. Toggle the fog on/off (🌫 / 👁 in the top bar,
  or `config.FOG_OF_WAR`) to inspect the exact numbers.
- **Save & load** — multiple named save slots plus autosave, with fully reproducible simulations
  (the RNG state is part of the save). In the web app you can also **export** a career to a file
  and **import** it later. On the hosted site that file is the only lasting copy, because server
  storage is wiped whenever the host sleeps or updates; run `hoopsim-web` locally to keep saves on
  your own disk.

## How a season flows

```
Preseason → Regular Season → Play-In → Playoffs → Draft → Free Agency → Offseason → (next year)
```

You advance at your own pace: watch or quick-sim your next game, simulate a week, or in the web
app sim straight to the trade deadline or the end of the season. Sim-to stops early when a trade
offer arrives or one of your players is hurt, and the playoffs can be simmed to the end. The web
app also reminds you to export your save when the regular season and the playoffs finish.

## Project layout

```
hoopsim/
  config.py          # all tunables (cap numbers, ratings scale, pace, injury rates…)
  rng.py             # seedable, save-restorable RNG
  models/            # pure data: player, team, contract, tactics, league, draft, world
  gen/               # procedural generation: names, players, NBA league, college world
  sim/               # engine (possessions + PBP), ratings, boxscore, season, playoffs,
                     #   college_tourney (single-elim conference + national tournaments)
  systems/           # cap, trades, free agency, draft, development, offseason, injuries,
                     #   carousel (coaching), news
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

340 tests, about two to three minutes. They cover box-score reconciliation, realistic stat
distributions, schedule/standings correctness, cap legality, trade validation, draft/development,
injuries and conditioning, the coaching carousel, the news wire, and byte-identical save
round-trips with reproducible RNG.

Statistical assertions pool across several seeds rather than trusting one: a single simulated
season is noisy enough that an effect can invert on an unlucky seed.

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

Newest — **legacy, free agency, and player identity**: a **career legacy system** now gives every
playthrough long-term stakes — players accrue **accolades** (MVP, All-League, DPOY, Champion, …),
cross **career milestones** (20,000 points and the like), and retire into a **Hall of Fame** (gated
by a weighted résumé score) and **all-time leaderboards** browsable in the History tab. To make it
matter from day one, world creation now fabricates a **synthetic backstory** — believable career
arcs and accolades for existing veterans plus a cohort of **retired legends** seeding the record
book — and every player carries **draft provenance** (year / round / pick) on his bio. **Free-agent
signings are now a real negotiation**: you trade contract **years against money** (more years is
security a player discounts for — strongly for lesser/older free agents, barely for young stars;
fewer years makes them hold out for a raise), instead of auto-accepting any offer that meets the
ask. The **team-selection screen shows projected strength** (stars by league-relative rank plus a
rating) so franchises read as unequal, and elite players can roll **rare "unicorn" archetypes** —
*Point Forward*, *Playmaking Big*, *Two-Way Phenom*, *Shot Creator* — that the normal pool never
produces.

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

Latest — **availability, the bench behind the bench, and a league that talks about itself**:

**Injuries are now a system rather than a counter.** Players carry a **condition** that drains
with minutes and recovers on light nights, so a star riding 38 minutes a night wears down over a
season while a bench player stays fresh. Wear-and-tear injuries roll off durability, condition,
age and workload; coming back opens a **return-to-play window** where re-injury is likelier and
tends to be worse, so a serious injury echoes forward instead of resetting the day a player is
cleared. Injuries have real names and sensible lengths — a torn ACL costs a season, a jammed
finger costs a week — and every player keeps a permanent **injury history**. You can **rest**
anyone to bank condition, though a roster too thin to field a rotation will play its healthy
bodies regardless. Crucially, **durability is now rolled independently of talent**: it used to
track a player's overall, which meant fragile players were always scrubs and an injury-prone star
was impossible. Glass-cannon stars exist now, and they miss about twice the games durable players
do.

**Coaching is a decision.** Head coaches carry a **career record that travels with them between
jobs**, so the hiring pool is something you can read — a 480-390 retread is a different bet from
an unproven first-timer. Bad seasons get coaches fired (about six benches a year league-wide),
vacancies fill from the market, and tenure splits hard by success. You also hire an **assistant
staff** from the owner's budget: a *Player Development* coach grows your young players faster, an
*Athletic Trainer* cuts injuries, a *Strength & Conditioning* coach keeps legs fresh into spring,
and a *Head Scout* tightens your read on draft prospects. A full elite staff is out of reach, so
it's a real tradeoff.

**A league news wire** ties it all together: injuries, big performances, win streaks, trades,
signings, draft picks, awards, career milestones, Hall of Fame inductions, retirements and the
coaching carousel all surface in one filterable feed, so the league finally reads like it's
happening rather than sitting in tables.

Alongside these, a **box-score rebalance** brought three distributions in line with the real NBA:
assist leaders now run around 11 a game (and are mostly guards, as they should be) instead of
topping out under 7, free-throw shooting sits near 78% with elite shooters no longer superhuman,
and rebounds land near 43 a team once team rebounds stopped being credited to individuals.

Still on the roadmap:

- **International prospects** entering via the NBA draft and recruitable to college programs.
- **Transfer portal** for college rosters.
- **Advanced NBA cap** rules (apron, sign-and-trade), two-way / G-League contracts.
- A richer **NIL marketplace** (negotiated endorsement packages, brand events).
- **Owner expectations and job security** — a mandate you're measured against, and a hot seat of
  your own.

### Future work (not started)

Trades & draft assets
- **Pick protections & swaps** (conditional picks, top-N protections rolling to the next year).

Coach mode — end-of-game situations (NBA & CBB)
- **Interactive crunch-time coaching is built** across the terminal and web app (NBA & college,
  regular season + postseason — including the college tournament in the browser).

Tiered signing — free agency & recruiting (built)
- Both markets now resolve in **waves** in the terminal and the web app alike, instead of a single
  instant pass.
- **Rounds of free agency**: the market opens in tiers — max-contract caliber first, then each wave
  widens to the next group down. You work the open tier each wave; players you pass on can be gone
  once rival GMs bid, and anyone still unsigned **re-prices downward** as their tier cools
  ([`fa_wave_pool`/`wave_market_salary`](hoopsim/systems/freeagency.py)).
- **Phased recruiting** for both scholarship and NIL: five-star prospects commit first, then four-,
  three-, and the rest. Missing a target leaves the lower tiers on the board, so you can pivot down
  instead of losing the whole class ([`recruit_wave_pool`/`resolve_recruiting_wave`](hoopsim/systems/recruiting.py)).

Coaching & rotations (built)
- Every team has a **head coach** with an archetype that gives it a rotation identity
  ([`models/coach.py`](hoopsim/models/coach.py)). A handful are outliers — *Seven Seconds* (run-and-gun),
  *Iron Rotation* (rides a 7-man core 40+ minutes), *Deep Bench*, *Motion Egalitarian* — while most
  carry a lean (*Pace & Space*, *Grind It Out*, *Defensive Anchor*) or are *Balanced*. The archetype
  seeds the team's default tactics and shapes `set_auto_minutes` (rotation depth, how hard minutes
  pile onto stars, starter caps) and `choose_lineup` (how readily tired players sit), so depth charts
  finally matter differently from team to team. The coach shows on the Tactics screen.
- **Position-aware lineups**: the engine now fills the five with a soft position-fit penalty, so it
  never fields five guards — each position's depth carries weight ([`choose_lineup`](hoopsim/sim/engine.py)).
- **User-controlled rotation**: the Lineup tab has **Rotation** and **End of Bench** tiers on top of
  the starting five. Pinned reserves (`team.rotation`) draw minutes; End-of-Bench players sit unless
  injuries force them in — so you can give a low-rated, high-upside youngster real run over a deeper
  veteran (which also accelerates his development). No manual rotation falls back to the coach's
  automatic shape ([`set_auto_minutes`](hoopsim/models/team.py)).

Rotations & depth chart (built)
- **Role tags** — `sixth_man`, `defensive_ace`, `closer` — bias the rotation math from the Lineup
  tab (terminal & web): a **closer** overrides crunch-time selection (taking the floor to close
  unless fouled out), a **defensive ace** earns extra minutes scaled by the opponent's offensive
  strength, and a **sixth man** jumps the bench queue (first reserve off the bench, most reserve
  minutes). One player per role; cleared automatically if he leaves the roster
  ([`team.roles`](hoopsim/models/team.py), [`choose_lineup`](hoopsim/sim/engine.py)).

## Notes

- Teams and players are entirely fictional and procedurally generated.
- A league is created from a random seed shown when you start a career; the same seed reproduces
  the same league **on the same build**. Changes to how players are generated shift the whole
  random stream, so a seed shared across versions will not rebuild an identical league — the
  durability rework in the injury update is one such change. Saves are unaffected: every field
  added since has a default, so older saves load and continue normally.

## License

Licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). You're free to fork,
modify, and share it for any **noncommercial** purpose. Commercial use is not permitted.
