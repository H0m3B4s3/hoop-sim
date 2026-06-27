"""Game presentation: line score, optional play-by-play, and box scores."""
from __future__ import annotations

from hoopsim.models.league import Game
from hoopsim.models.world import World
from hoopsim.ui.console import clear, confirm, console, pause
from hoopsim.ui.widgets import box_score_table, header, line_score_panel, play_by_play


def present_result(world: World, game: Game, result, *, watched: bool,
                   coached: bool = False) -> None:
    away, home = world.teams[result.away_tid], world.teams[result.home_tid]
    if coached:
        pause("Press Enter for the final")
    clear()
    header(world)
    console.print()
    console.print(line_score_panel(world, result))

    # When the user coached the finish live they've already seen the crunch, so the full
    # replay is offered but defaults to off.
    if watched and result.pbp:
        if confirm("Watch the full play-by-play?", default=not coached):
            clear()
            console.rule(f"[title]{away.abbrev} @ {home.abbrev}[/title]", style="muted")
            play_by_play(world, result)
            pause("Press Enter for the box score")

    clear()
    header(world)
    console.print(line_score_panel(world, result))
    console.print(box_score_table(world, result, result.away_tid))
    console.print(box_score_table(world, result, result.home_tid))
    pause()


def result_one_liner(world: World, game: Game) -> str:
    away, home = world.teams[game.away], world.teams[game.home]
    win = home if game.home_score > game.away_score else away
    return (f"{away.abbrev} {game.away_score} @ {home.abbrev} {game.home_score} "
            f"→ [{win.color}]{win.abbrev}[/]")
