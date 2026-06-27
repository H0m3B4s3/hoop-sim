"""League-wide scouting board: browse every player's attributes to find trade targets.

A read-only aggregation over the whole league (rostered players plus free agents). The board
is sortable (overall, potential, age, or any composite) and filterable by position, team, and
trade-block status, so a GM can hunt for targets and see who's being shopped.
"""
from __future__ import annotations

from typing import Dict, List, Set

from rich.table import Table

from hoopsim.models.attributes import COMPOSITES, all_composites
from hoopsim.models.player import Player
from hoopsim.models.world import World
from hoopsim.systems import trades

from hoopsim.ui.console import ask_int, choose, clear, console, pause
from hoopsim.ui.theme import ovr_style
from hoopsim.ui.widgets import header, player_card

_PAGE = 18
_SORTS = [("overall", "Overall"), ("potential", "Potential"), ("age", "Age")] + \
         [(c, c.title()) for c in COMPOSITES]


def _comp(p: Player, key: str) -> int:
    return round(all_composites(p.ratings)[key])


def _sort_key(p: Player, sort: str):
    if sort == "overall":
        return p.overall
    if sort == "potential":
        return p.scouted_potential()
    if sort == "age":
        return -p.age            # youngest first when sorting "best"
    return _comp(p, sort)


def scouting_screen(world: World) -> None:
    pos_filter = "All"
    team_filter = "All"
    block_only = False
    sort = "overall"
    page = 0

    # league-wide trade-block membership (other teams only)
    block: Set[int] = set()
    for t in world.team_list():
        if t.tid != world.user_team_id:
            block.update(trades.team_trade_block(world, t))

    while True:
        players = _gather(world)
        if pos_filter != "All":
            players = [p for p in players
                       if pos_filter in (p.position, p.secondary_position)]
        if team_filter != "All":
            players = [p for p in players if _team_abbrev(world, p) == team_filter]
        if block_only:
            players = [p for p in players if p.pid in block]
        players.sort(key=lambda p: _sort_key(p, sort), reverse=True)

        pages = max(1, (len(players) + _PAGE - 1) // _PAGE)
        page = max(0, min(page, pages - 1))
        start = page * _PAGE
        shown = players[start:start + _PAGE]

        clear()
        header(world)
        sort_label = dict(_SORTS)[sort]
        console.print(f"[title]League Scouting Board[/title]   "
                      f"Sort: [accent]{sort_label}[/accent]   "
                      f"Pos: [accent]{pos_filter}[/accent]   "
                      f"Team: [accent]{team_filter}[/accent]   "
                      f"Block only: [accent]{'on' if block_only else 'off'}[/accent]\n")
        console.print(_table(world, shown, block, start))
        console.print(f"[dim]Showing {start + 1}-{start + len(shown)} of {len(players)} players "
                      f"· page {page + 1}/{pages} · [accent]✦[/accent] = on the trade block[/dim]")

        opts = [("ratings", "🔍  View a player's full ratings (enter its #)"),
                ("sort", "↕   Sort by…")]
        if page < pages - 1:
            opts.append(("next", "▶  Next page"))
        if page > 0:
            opts.append(("prev", "◀  Previous page"))
        opts += [("pos", "🔎  Filter by position"),
                 ("team", "🏟   Filter by team"),
                 ("block", f"✦   Trade block {'off' if block_only else 'on'}"),
                 ("back", "← Back")]
        action = choose("", opts)
        if action == "ratings":
            n = ask_int("Player # to scout", default=0)
            if 1 <= n <= len(shown):
                clear()
                header(world)
                console.print(player_card(world, shown[n - 1]))
                pause()
        elif action == "sort":
            choice = choose("Sort by which attribute?", _SORTS, allow_back=True)
            if choice:
                sort = choice
                page = 0
        elif action == "next":
            page += 1
        elif action == "prev":
            page -= 1
        elif action == "pos":
            from hoopsim.models.attributes import POSITIONS
            choice = choose("Show which position?",
                            [("All", "All positions")] + [(p, p) for p in POSITIONS])
            pos_filter = choice or pos_filter
            page = 0
        elif action == "team":
            opts_t = [("All", "All teams")] + [
                (t.abbrev, f"[{t.color}]{t.abbrev}[/] {t.full_name}")
                for t in sorted(world.team_list(), key=lambda t: t.abbrev)]
            choice = choose("Show which team?", opts_t, allow_back=True)
            if choice:
                team_filter = choice
                page = 0
        elif action == "block":
            block_only = not block_only
            page = 0
        else:
            return


def _gather(world: World) -> List[Player]:
    out: List[Player] = []
    for t in world.team_list():
        out.extend(world.players[pid] for pid in t.roster if pid in world.players)
    out.extend(world.free_agent_players())
    return out


def _team_abbrev(world: World, p: Player) -> str:
    t = world.find_team(p.team_id) if p.team_id is not None else None
    return t.abbrev if t else "FA"


def _table(world: World, players: List[Player], block: Set[int], start: int) -> Table:
    table = Table(header_style="label")
    table.add_column("#", justify="right")
    table.add_column("Name", no_wrap=True)
    table.add_column("Tm")
    table.add_column("Pos")
    table.add_column("Age", justify="right")
    table.add_column("OVR", justify="right")
    table.add_column("POT", justify="right")
    for c in COMPOSITES:
        table.add_column(c[:3].upper(), justify="right")
    table.add_column("Blk", justify="center")
    for i, p in enumerate(players, start=1):
        comps = all_composites(p.ratings)
        pos = p.position + (f"/{p.secondary_position}" if p.secondary_position else "")
        table.add_row(
            str(i), p.name, _team_abbrev(world, p), pos, str(p.age),
            f"[{ovr_style(p.overall)}]{p.overall}[/]", str(p.scouted_potential()),
            *[str(round(comps[c])) for c in COMPOSITES],
            "[accent]✦[/accent]" if p.pid in block else "",
        )
    return table
