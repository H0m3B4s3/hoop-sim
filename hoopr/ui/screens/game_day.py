"""Game presentation: line score, optional play-by-play, and box scores."""
from __future__ import annotations

from hoopr.models.league import Game
from hoopr.models.world import World
from hoopr.ui.console import clear, confirm, console, pause
from hoopr.ui.widgets import (box_score_table, header, line_score_panel, play_by_play,
                              team_text)


def present_result(world: World, game: Game, result, *, watched: bool) -> None:
    away, home = world.teams[result.away_tid], world.teams[result.home_tid]
    clear()
    header(world)
    console.print()
    console.print(line_score_panel(world, result))

    if watched and result.pbp:
        if confirm("Watch the play-by-play?", default=True):
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
