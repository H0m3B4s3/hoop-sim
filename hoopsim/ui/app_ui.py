"""Top-level interactive game loop: title, new career, and the phase-aware game hub."""
from __future__ import annotations

import random
from typing import List, Optional, Tuple

from rich.panel import Panel
from rich.table import Table

from hoopsim import __version__
from hoopsim.config import CONFERENCES, SEASON_PRESETS
from hoopsim.models.league import Game, Phase
from hoopsim.models.world import World
from hoopsim.save import store
from hoopsim.sim import playoffs as P
from hoopsim.sim import season as S
from hoopsim.systems import offseason
from hoopsim.ui.console import ask_text, choose, clear, confirm, console, pause
from hoopsim.ui.screens.finances import show_finances
from hoopsim.ui.screens.free_agency import free_agent_screen
from hoopsim.ui.screens.game_day import present_result, result_one_liner
from hoopsim.ui.screens.roster import show_roster
from hoopsim.ui.screens.standings import show_standings
from hoopsim.ui.screens.tactics import edit_tactics
from hoopsim.ui.screens.trade import trade_screen
from hoopsim.ui.widgets import bracket_panel, header


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
def main_loop() -> None:
    while True:
        clear()
        _title()
        action = choose("", [
            ("new", "New Career"),
            ("load", "Load Game"),
            ("quit", "Quit"),
        ])
        if action == "new":
            world = new_career()
            if world:
                game_hub(world)
        elif action == "load":
            world = load_career()
            if world:
                game_hub(world)
        elif action == "quit":
            console.print("[dim]Thanks for playing HoopSim.[/dim]")
            return


def _title() -> None:
    from rich.text import Text
    art = ("  _   _  ___   ___  ___ ___ \n"
           " | | | |/ _ \\ / _ \\| _ \\ _ \\\n"
           " | |_| | (_) | (_) |  _/   /\n"
           "  \\___/ \\___/ \\___/|_| |_|_\\")
    banner = Text(art, style="bold cyan")
    banner.append(f"\nBasketball Management Simulation · v{__version__}", style="dim")
    console.print(Panel(banner, border_style="accent", padding=(1, 4)))


# ---------------------------------------------------------------------------
# New career / load
# ---------------------------------------------------------------------------
def new_career() -> Optional[World]:
    clear()
    console.print(Panel("[title]New Career[/title]\n"
                        "[dim]Choose your league. The college and NBA layers are connected by the "
                        "draft pipeline.[/dim]", border_style="accent"))
    league = choose("Which league do you want to manage?", [
        ("nba", "🏀 NBA franchise — cap, trades, free agency, draft"),
        ("college", "🎓 College program — recruiting, a season, March-style tournament"),
    ])
    if league is None:
        return None
    seed = _choose_seed()
    if league == "college":
        return _new_college_career(seed)
    return _new_nba_career(seed)


def _choose_seed() -> int:
    """Let the player paste a seed to reproduce/share a world, or roll a fresh random one."""
    raw = ask_text("World seed (blank = random)", default="").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            console.print("[warn]Not a number — using a random seed.[/warn]")
    return random.randrange(1 << 30)


def _new_nba_career(seed: int) -> Optional[World]:
    preset = choose("Season length", [
        ("Standard", "Standard — 82 games"),
        ("Quick", "Quick — 30 games (faster sims)"),
    ])
    if preset is None:
        return None
    with console.status("[accent]Generating league…[/accent]", spinner="dots"):
        from hoopsim.gen.leaguegen import build_world
        world = build_world(seed=seed, season_preset=preset)
    tid = _choose_team(world)
    if tid is None:
        return None
    world.user_team_id = tid
    S.start_season(world)
    store.autosave(world)
    clear()
    console.print(Panel(f"You are now the GM of the [bold {world.teams[tid].color}]"
                        f"{world.teams[tid].full_name}[/].\n[dim]League seed {seed} · "
                        f"{SEASON_PRESETS[preset]}-game season[/dim]",
                        title="[good]Career Started[/good]", border_style="good"))
    pause()
    return world


def _new_college_career(seed: int) -> Optional[World]:
    economy = choose("Choose your college economy (locked for this save)", [
        ("scholarship", "🎓 Scholarship mode — traditional 13-scholarship limit & allocation"),
        ("nil", "💸 NIL mode — recruit with NIL money & marketability, grow brand value"),
    ])
    if economy is None:
        return None
    with console.status("[accent]Generating the college landscape…[/accent]", spinner="dots"):
        from hoopsim.gen.collegegen import build_college_world
        world = build_college_world(seed=seed, economy=economy)
    tid = _choose_team(world)
    if tid is None:
        return None
    world.user_team_id = tid
    S.start_season(world)
    store.autosave(world)
    clear()
    econ = "NIL" if economy == "nil" else "Scholarship"
    console.print(Panel(f"You are now the head coach of the [bold {world.teams[tid].color}]"
                        f"{world.teams[tid].full_name}[/] "
                        f"([star]{'★' * world.teams[tid].prestige}[/star]).\n"
                        f"[dim]{econ} mode · seed {seed} · declared players feed the NBA draft.[/dim]",
                        title="[good]Career Started[/good]", border_style="good"))
    pause()
    return world


def _choose_team(world: World) -> Optional[int]:
    from hoopsim.sim import power
    from hoopsim.ui.screens.standings import world_conferences
    college = world.mode == "college"
    stars = power.strength_stars(world)
    strength = power.projected_strength(world)
    options: List[Tuple[str, str]] = []
    for conf in world_conferences(world):
        for t in sorted((t for t in world.team_list() if t.conference == conf),
                        key=lambda t: t.city):
            if college:
                tag = "★" * t.prestige
            else:
                tag = f"{'★' * stars.get(t.tid, 3)}  {strength.get(t.tid, 70)} OVR"
            options.append((str(t.tid),
                            f"[{t.color}]{t.abbrev}[/] {t.full_name} "
                            f"[dim]({conf}) {tag}[/dim]"))
    key = choose("Choose your program" if world.mode == "college" else "Choose your franchise",
                 options)
    return int(key) if key is not None else None


def load_career() -> Optional[World]:
    slots = store.list_saves()
    if not slots:
        console.print("[warn]No saved games found.[/warn]")
        pause()
        return None
    options = [(s, s) for s in slots]
    key = choose("Load which save?", options, allow_back=True)
    if key is None:
        return None
    try:
        with console.status("[accent]Loading…[/accent]"):
            world = store.load_game(key)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[bad]Failed to load: {exc}[/bad]")
        pause()
        return None
    return world


# ---------------------------------------------------------------------------
# Game hub — dispatches by season phase
# ---------------------------------------------------------------------------
def game_hub(world: World) -> None:
    if world.mode == "college":
        from hoopsim.ui.college_ui import college_hub
        college_hub(world)
        return
    while True:
        phase = world.phase
        if phase == Phase.REGULAR_SEASON:
            if S.regular_season_complete(world):
                _enter_playoffs(world)
                continue
            if _regular_season_menu(world) == "quit":
                return
        elif phase == Phase.PLAYOFFS:
            if _playoffs_menu(world) == "quit":
                return
        elif phase in (Phase.DRAFT, Phase.FREE_AGENCY, Phase.OFFSEASON):
            _run_offseason(world)
        else:  # preseason or anything unexpected
            S.start_season(world)


# ---------------------------------------------------------------------------
# Regular season
# ---------------------------------------------------------------------------
def _regular_season_menu(world: World) -> Optional[str]:
    clear()
    header(world)
    nxt = S.user_next_game(world)
    if nxt:
        opp = world.teams[nxt.opponent_of(world.user_team_id)]
        home = "vs" if nxt.home == world.user_team_id else "@"
        console.print(f"  Next game: [label]{home} {opp.full_name}[/label] "
                      f"[dim](day {nxt.day + 1})[/dim]\n")
    action = choose("", [
        ("watch", "▶  Watch next game (play-by-play)"),
        ("quick", "⏩  Quick-sim next game"),
        ("week", "📅  Simulate a week"),
        ("roster", "👥  Roster"),
        ("lineup", "🧩  Set lineup"),
        ("tactics", "📋  Tactics"),
        ("front", "🏢  Front Office (trade · sign · finances)"),
        ("scout", "🔍  Scouting board (league-wide)"),
        ("standings", "📊  Standings"),
        ("leaders", "🏀  League leaders"),
        ("legacy", "🏅  Legacy & history"),
        ("save", "💾  Save game"),
        ("quit", "🚪  Quit to main menu"),
    ])
    if action == "watch":
        _play_user_game(world, watch=True)
    elif action == "quick":
        _play_user_game(world, watch=False)
    elif action == "week":
        _sim_span(world, days=4)
    elif action == "roster":
        show_roster(world)
    elif action == "lineup":
        from hoopsim.ui.screens.lineup import lineup_screen
        lineup_screen(world)
    elif action == "tactics":
        edit_tactics(world)
    elif action == "front":
        _front_office(world)
    elif action == "scout":
        from hoopsim.ui.screens.scouting import scouting_screen
        scouting_screen(world)
    elif action == "standings":
        show_standings(world)
    elif action == "leaders":
        _league_leaders(world)
    elif action == "legacy":
        from hoopsim.ui.screens.legacy import legacy_screen
        legacy_screen(world)
    elif action == "save":
        _save_menu(world)
    elif action == "quit":
        if confirm("Save before quitting?", default=True):
            _save_menu(world)
        return "quit"
    return None


def _front_office(world: World) -> None:
    while True:
        clear()
        header(world)
        action = choose("Front Office", [
            ("trade", "🤝  Propose a trade"),
            ("sign", "✍️   Sign a free agent"),
            ("extend", "📝  Re-sign / extend a player"),
            ("finances", "💰  Finances & contracts"),
            ("back", "← Back"),
        ])
        if action == "trade":
            trade_screen(world)
        elif action == "sign":
            free_agent_screen(world)
        elif action == "extend":
            from hoopsim.ui.screens.extend import extend_screen
            extend_screen(world)
        elif action == "finances":
            show_finances(world)
        else:
            return


def _make_live_coach(world: World, game: Game):
    """A live crunch-time coach for the user's own game (regular season or playoffs)."""
    uid = world.user_team_id
    if uid is None or not game.involves(uid):
        return None
    from hoopsim.ui.screens.live_coach import LiveCoach
    return LiveCoach(world, uid, game.home, game.away)


def _play_user_game(world: World, watch: bool) -> None:
    game = S.user_next_game(world)
    if game is None:
        with console.status("[accent]Simulating remaining league games…[/accent]"):
            while not S.regular_season_complete(world):
                S.advance_one_day(world)
        console.print("[dim]Your team's regular season is complete.[/dim]")
        pause()
        return
    with console.status("[accent]Simulating up to your game…[/accent]"):
        while world.day < game.day:
            S.advance_one_day(world)
    coach = _make_live_coach(world, game) if watch else None
    _, user_result = S.advance_one_day(world, watch_user=watch, coach=coach)
    present_result(world, game, user_result, watched=watch,
                   coached=bool(coach and coach.engaged))


def _sim_span(world: World, days: int) -> None:
    uid = world.user_team_id
    user_games: List[Game] = []
    with console.status("[accent]Simulating…[/accent]"):
        for _ in range(days):
            if S.regular_season_complete(world):
                break
            results, _ = S.advance_one_day(world)
            user_games += [g for g, _ in results if g.involves(uid)]
    clear()
    header(world)
    if user_games:
        console.print("[title]Recent results[/title]")
        for g in user_games:
            console.print("  " + result_one_liner(world, g))
    else:
        console.print("[dim]No games for your team in this span.[/dim]")
    pause()


# ---------------------------------------------------------------------------
# Playoffs
# ---------------------------------------------------------------------------
def _enter_playoffs(world: World) -> None:
    clear()
    header(world)
    console.print(Panel("[title]Regular season complete![/title]", border_style="accent"))
    show_standings_inline(world)
    pause("Press Enter to begin the postseason")
    log = P.start_playoffs(world)
    store.autosave(world)
    clear()
    console.print(Panel("\n".join(log) or "Seeds locked.",
                        title="[accent]Play-In Tournament[/accent]", border_style="accent"))
    pause()


def show_standings_inline(world: World) -> None:
    from rich.columns import Columns
    from hoopsim.ui.widgets import standings_table
    console.print(Columns([standings_table(world, c) for c in CONFERENCES],
                          padding=(0, 4), equal=True))


def _user_eliminated(world: World) -> bool:
    uid = world.user_team_id
    for s in world.bracket.get("all_series", []):
        if s["winner"] is not None and uid in (s["hi"], s["lo"]) and s["winner"] != uid:
            return True
    return False


def _user_active_series(world: World):
    uid = world.user_team_id
    for s in P.active_series(world):
        if uid in (s["hi"], s["lo"]):
            return s
    return None


def _playoffs_menu(world: World) -> Optional[str]:
    clear()
    header(world)
    console.print(bracket_panel(world))
    eliminated = _user_eliminated(world)
    active = _user_active_series(world)
    if active:
        opp = world.teams[active["lo"] if active["hi"] == world.user_team_id else active["hi"]]
        console.print(f"  Your series: [label]{P.series_status(world, active)}[/label] "
                      f"vs {opp.full_name}\n")
    elif eliminated:
        console.print("  [bad]Your team has been eliminated.[/bad]\n")

    opts = []
    if active:
        opts.append(("watch", "▶  Watch your next playoff game"))
    opts += [
        ("advance", "⏩  Advance series (sim a slate)"),
        ("round", "⏭  Sim to end of round"),
        ("end", "🏁  Sim to end of playoffs"),
        ("roster", "👥  Roster"),
        ("save", "💾  Save game"),
        ("quit", "🚪  Quit to main menu"),
    ]
    action = choose("", opts)
    if action == "watch":
        _advance_playoffs(world, watch=True)
    elif action == "advance":
        _advance_playoffs(world, watch=False)
    elif action == "round":
        _sim_playoff_round(world)
    elif action == "end":
        _sim_playoffs_to_end(world)
    elif action == "roster":
        show_roster(world)
    elif action == "save":
        _save_menu(world)
    elif action == "quit":
        if confirm("Save before quitting?", default=True):
            _save_menu(world)
        return "quit"
    return None


def _advance_playoffs(world: World, watch: bool) -> None:
    coach = None
    if watch:
        matchup = P.user_next_matchup(world)
        if matchup is not None:
            from hoopsim.ui.screens.live_coach import LiveCoach
            home, away = matchup
            coach = LiveCoach(world, world.user_team_id, home, away)
    if coach is not None:
        # Live coaching prints to the console, so it can't run under a status spinner.
        results, user_result = P.advance_playoff_slate(world, watch_user=watch, coach=coach)
    else:
        with console.status("[accent]Simulating playoff games…[/accent]"):
            results, user_result = P.advance_playoff_slate(world, watch_user=watch)
    if watch and user_result is not None:
        # find the user's game object for presentation
        game = _last_user_playoff_game(world)
        if game is not None:
            present_result(world, game, user_result, watched=True,
                           coached=bool(coach and coach.engaged))
            return
    clear()
    header(world)
    console.print(bracket_panel(world))
    if results:
        console.print("\n[title]Slate results[/title]")
        for s, res in results:
            console.print("  " + _series_line(world, s, res))
    pause()


def _series_line(world, s, res) -> str:
    a, h = world.teams[res.away_tid], world.teams[res.home_tid]
    return (f"[{a.color}]{a.abbrev}[/] {res.away_score} @ [{h.color}]{h.abbrev}[/] "
            f"{res.home_score}   [dim]({P.series_status(world, s)})[/dim]")


def _last_user_playoff_game(world: World) -> Optional[Game]:
    uid = world.user_team_id
    user_pos = [g for g in world.schedule if g.is_playoff and g.involves(uid) and g.played]
    return user_pos[-1] if user_pos else None


def _sim_playoff_round(world: World) -> None:
    start_round = world.bracket["round"]
    with console.status("[accent]Simulating round…[/accent]"):
        while world.bracket and world.bracket["round"] == start_round \
                and not P.playoffs_complete(world):
            P.advance_playoff_slate(world)
    clear()
    header(world)
    console.print(bracket_panel(world))
    pause()


def _sim_playoffs_to_end(world: World) -> None:
    with console.status("[accent]Simulating the playoffs…[/accent]"):
        guard = 0
        while not P.playoffs_complete(world):
            P.advance_playoff_slate(world)
            guard += 1
            if guard > 400:
                break
    clear()
    console.print(bracket_panel(world))
    pause()


# ---------------------------------------------------------------------------
# Offseason
# ---------------------------------------------------------------------------
def _run_offseason(world: World) -> None:
    champ = P.champion(world)
    clear()
    if champ is not None:
        console.print(Panel(f"[star]🏆 {world.teams[champ].full_name} win the championship![/star]",
                            border_style="accent"))
        pause("Press Enter to begin the offseason")
    with console.status("[accent]Player development & expiring contracts…[/accent]"):
        summary = offseason.pre_draft(world, champ)

    # 1) Draft (interactive)
    from hoopsim.ui.screens.draft import draft_screen
    draft_screen(world)
    offseason.enforce_roster_max(world)

    # 2) Free agency — the user signs first, then the AI fills out the league.
    _offseason_free_agency(world)

    # 3) Finalize and tip off the new season.
    offseason.post_offseason(world)
    store.autosave(world)
    clear()
    console.print(Panel(
        f"Season {world.season_year} is underway.\n"
        f"[dim]Retired this offseason: {summary['retired']} · "
        f"Re-signed by their teams: {summary.get('resigned', 0)} · "
        f"Players who reached free agency: {summary['new_fas']}[/dim]",
        title="[good]New Season[/good]", border_style="good"))
    pause()


def _offseason_free_agency(world: World) -> None:
    from hoopsim.systems import freeagency
    clear()
    header(world)
    console.print(Panel(
        "[title]Free Agency[/title]\n[dim]The market opens in waves — the top tier signs first, then "
        "each wave widens to the next caliber down. Pursue your targets each wave; players you pass "
        "on may be gone when rival GMs bid, and whoever lingers re-prices downward.[/dim]",
        border_style="accent"))
    pause()
    freeagency.start_fa_market(world)
    while world.fa_wave is not None:
        wave = world.fa_wave
        free_agent_screen(world)            # user works the open tier; "Done" exits the screen
        with console.status(f"[accent]Rival GMs bidding — wave {wave + 1} "
                            f"({freeagency.FA_WAVE_NAMES[wave]})…[/accent]"):
            signed = freeagency.run_fa_wave(world)["signings"]
        more = freeagency.advance_fa_wave(world)
        clear()
        header(world)
        msg = f"[dim]Rival GMs signed {signed} free agent(s) in this wave.[/dim]"
        if more:
            console.print(Panel(f"{msg}\nThe next wave opens — "
                                f"[accent]{freeagency.FA_WAVE_NAMES[world.fa_wave]}[/accent].",
                                border_style="accent"))
            pause("Press Enter for the next wave")
        else:
            console.print(Panel(f"{msg}\nFree agency is closed.", border_style="good"))
            pause()


# ---------------------------------------------------------------------------
# League leaders & save menu
# ---------------------------------------------------------------------------
def _league_leaders(world: World) -> None:
    clear()
    header(world)
    qualified = [p for p in world.players.values() if p.season.gp >= max(1, world.day // 4)]

    def leader_table(stat: str, label: str, fmt) -> Table:
        table = Table(title=label, title_style="title", header_style="label")
        table.add_column("#", justify="right")
        table.add_column("Player")
        table.add_column(label.split()[0], justify="right")
        ranked = sorted(qualified, key=lambda p: getattr(p.season, stat), reverse=True)[:5]
        for i, p in enumerate(ranked, 1):
            team = world.teams.get(p.team_id)
            tag = f"[{team.color}]{team.abbrev}[/]" if team else "FA"
            table.add_row(str(i), f"{p.short_name} {tag}", fmt(p.season))
        return table

    from rich.columns import Columns
    console.print(Columns([
        leader_table("ppg", "PPG", lambda s: f"{s.ppg:.1f}"),
        leader_table("rpg", "RPG", lambda s: f"{s.rpg:.1f}"),
        leader_table("apg", "APG", lambda s: f"{s.apg:.1f}"),
    ], padding=(0, 3)))
    pause()


def _save_menu(world: World) -> None:
    default = f"{world.user_team.abbrev}_{world.season_year}"
    name = ask_text("Save slot name", default=default)
    path = store.save_game(world, name)
    console.print(f"[good]Saved to[/good] [dim]{path}[/dim]")
    pause()
