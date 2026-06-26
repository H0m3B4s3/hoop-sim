"""College-mode game hub: regular season, conference + national tournaments, and the offseason
(development, eligibility, the NBA draft pipeline, and recruiting)."""
from __future__ import annotations

from typing import Optional

from rich.panel import Panel
from rich.table import Table

from hoopr.models.league import Phase
from hoopr.models.world import World
from hoopr.save import store
from hoopr.sim import college_tourney as CT
from hoopr.systems import college_offseason as CO
from hoopr.ui import app_ui
from hoopr.ui.console import choose, clear, confirm, console, pause
from hoopr.ui.screens.college_fin import college_finance_screen
from hoopr.ui.screens.game_day import present_result
from hoopr.ui.screens.recruiting import recruiting_screen
from hoopr.ui.screens.roster import show_roster
from hoopr.ui.screens.standings import show_standings
from hoopr.ui.screens.tactics import edit_tactics
from hoopr.ui.widgets import college_bracket_panel, header


def college_hub(world: World) -> None:
    while True:
        phase = world.phase
        if phase == Phase.REGULAR_SEASON:
            if app_ui.S.regular_season_complete(world):
                _enter_postseason(world)
                continue
            if _regular_menu(world) == "quit":
                return
        elif phase == Phase.PLAYOFFS:
            if _postseason_menu(world) == "quit":
                return
        elif phase in (Phase.DRAFT, Phase.OFFSEASON, Phase.FREE_AGENCY):
            _run_offseason(world)
        else:
            app_ui.S.start_season(world)


# ---------------------------------------------------------------------------
# Regular season
# ---------------------------------------------------------------------------
def _regular_menu(world: World) -> Optional[str]:
    clear()
    header(world)
    nxt = app_ui.S.user_next_game(world)
    if nxt:
        opp = world.teams[nxt.opponent_of(world.user_team_id)]
        loc = "vs" if nxt.home == world.user_team_id else "@"
        console.print(f"  Next game: [label]{loc} {opp.full_name}[/label] "
                      f"[dim](day {nxt.day + 1})[/dim]\n")
    fin_label = "💸 NIL collective" if world.college_economy == "nil" else "🎓 Scholarships"
    action = choose("", [
        ("watch", "▶  Watch next game (play-by-play)"),
        ("quick", "⏩  Quick-sim next game"),
        ("week", "📅  Simulate a week"),
        ("roster", "👥  Roster"),
        ("tactics", "📋  Tactics"),
        ("finance", fin_label),
        ("standings", "📊  Standings"),
        ("leaders", "🏀  Stat leaders"),
        ("save", "💾  Save game"),
        ("quit", "🚪  Quit to main menu"),
    ])
    if action == "watch":
        app_ui._play_user_game(world, watch=True)
    elif action == "quick":
        app_ui._play_user_game(world, watch=False)
    elif action == "week":
        app_ui._sim_span(world, days=4)
    elif action == "roster":
        show_roster(world)
    elif action == "tactics":
        edit_tactics(world)
    elif action == "finance":
        college_finance_screen(world)
    elif action == "standings":
        show_standings(world)
    elif action == "leaders":
        app_ui._league_leaders(world)
    elif action == "save":
        app_ui._save_menu(world)
    elif action == "quit":
        if confirm("Save before quitting?", default=True):
            app_ui._save_menu(world)
        return "quit"
    return None


# ---------------------------------------------------------------------------
# Postseason
# ---------------------------------------------------------------------------
def _enter_postseason(world: World) -> None:
    clear()
    header(world)
    console.print(Panel("[title]Regular season complete![/title] Conference tournaments are set.",
                        border_style="accent"))
    app_ui.show_standings_inline(world)
    pause("Press Enter to start the tournaments")
    CT.start_college_postseason(world)
    store.autosave(world)


def _postseason_menu(world: World) -> Optional[str]:
    clear()
    header(world)
    console.print(college_bracket_panel(world))
    alive = CT.user_still_alive(world)
    if not alive:
        console.print("  [bad]Your team has been eliminated — but the tournament rolls on.[/bad]\n")
    opts = []
    if alive:
        opts.append(("watch", "▶  Watch your next game"))
    opts += [
        ("advance", "⏩  Advance (sim a round of games)"),
        ("end", "🏁  Sim to the national champion"),
        ("roster", "👥  Roster"),
        ("save", "💾  Save game"),
        ("quit", "🚪  Quit to main menu"),
    ]
    action = choose("", opts)
    if action == "watch":
        _advance(world, watch=True)
    elif action == "advance":
        _advance(world, watch=False)
    elif action == "end":
        _sim_to_champion(world)
    elif action == "roster":
        show_roster(world)
    elif action == "save":
        app_ui._save_menu(world)
    elif action == "quit":
        if confirm("Save before quitting?", default=True):
            app_ui._save_menu(world)
        return "quit"
    return None


def _advance(world: World, watch: bool) -> None:
    with console.status("[accent]Simulating tournament games…[/accent]"):
        results, user_result = CT.advance_college_slate(world, watch_user=watch)
    if watch and user_result is not None:
        game = app_ui._last_user_playoff_game(world)
        if game is not None:
            present_result(world, game, user_result, watched=True)
            return
    clear()
    header(world)
    console.print(college_bracket_panel(world))
    pause()


def _sim_to_champion(world: World) -> None:
    with console.status("[accent]Playing out the tournament…[/accent]"):
        guard = 0
        while not CT.college_postseason_complete(world):
            CT.advance_college_slate(world)
            guard += 1
            if guard > 300:
                break
    clear()
    console.print(college_bracket_panel(world))
    pause()


# ---------------------------------------------------------------------------
# Offseason
# ---------------------------------------------------------------------------
def _run_offseason(world: World) -> None:
    champ = CT.national_champion(world)
    user_team = world.user_team
    clear()
    if champ is not None:
        crown = "[star]🏆 You won the National Championship![/star]" if champ == world.user_team_id \
            else f"[accent]National Champion: {world.teams[champ].full_name}[/accent]"
        console.print(Panel(crown, border_style="accent"))
        pause("Press Enter to begin the offseason")

    with console.status("[accent]Player development, declarations & the NBA Draft…[/accent]"):
        summary = CO.pre_recruiting(world, champ)

    _show_pipeline(world, user_team, summary)
    recruiting_screen(world)
    CO.post_recruiting(world)
    store.autosave(world)
    clear()
    console.print(Panel(
        f"The {world.season_year} season is underway.\n"
        f"[dim]Declared for the draft: {summary['declared']} · "
        f"Graduated: {summary['graduated']} · Returning: {summary['returning']}[/dim]",
        title="[good]New Season[/good]", border_style="good"))
    pause()


def _show_pipeline(world: World, user_team, summary: dict) -> None:
    clear()
    header(world)
    console.print(Panel(
        f"[title]Draft Pipeline[/title]  [dim]{summary['declared']} players declared · "
        f"{summary['drafted']} drafted into the NBA[/dim]", border_style="accent"))
    results = (world.pipeline or {}).get("results", [])
    mine = [r for r in results if r["college"] == user_team.full_name]
    if mine:
        table = Table(title="Your Players Drafted to the NBA", title_style="title",
                      header_style="label")
        table.add_column("Pick", justify="right")
        table.add_column("Player")
        table.add_column("NBA Team")
        for r in mine:
            nba = world.find_team(r["tid"])
            tag = f"[{nba.color}]{nba.abbrev}[/]" if nba else "?"
            table.add_row(f"#{r['pick']}", r["name"], tag)
        console.print(table)
    else:
        console.print("[dim]None of your players were drafted into the NBA this year.[/dim]")
    # show the lottery (top 5 overall)
    if results:
        top = Table(title="NBA Lottery (Top 5)", title_style="title", header_style="label")
        top.add_column("Pick", justify="right")
        top.add_column("Player")
        top.add_column("From")
        top.add_column("NBA Team")
        for r in results[:5]:
            nba = world.find_team(r["tid"])
            tag = f"[{nba.color}]{nba.abbrev}[/]" if nba else "?"
            top.add_row(f"#{r['pick']}", r["name"], r["college"], tag)
        console.print(top)
    pause()
