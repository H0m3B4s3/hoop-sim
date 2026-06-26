"""Free-agency screen: browse (paged, filterable) and sign free agents; waive to free a spot."""
from __future__ import annotations

from hoopr.config import ROSTER_MAX
from hoopr.models.attributes import POSITIONS
from hoopr.models.team import auto_set_lineup, roster_players
from hoopr.models.world import World
from hoopr.systems import cap, freeagency
from rich.table import Table

from hoopr.ui.console import ask_int, choose, clear, confirm, console, pause
from hoopr.ui.theme import ovr_style
from hoopr.ui.widgets import header, money, player_card

_PAGE = 18


def free_agent_screen(world: World) -> None:
    team = world.user_team
    pos_filter = "All"
    page = 0
    while True:
        fas = sorted(world.free_agent_players(), key=lambda p: p.overall, reverse=True)
        if pos_filter != "All":
            fas = [p for p in fas if p.position == pos_filter or p.secondary_position == pos_filter]
        pages = max(1, (len(fas) + _PAGE - 1) // _PAGE)
        page = max(0, min(page, pages - 1))
        start = page * _PAGE
        shown = fas[start:start + _PAGE]

        clear()
        header(world)
        space = cap.cap_space(world, team)
        full = len(team.roster) >= ROSTER_MAX
        mle = "[bad]used[/bad]" if team.mle_used else "[good]available[/good]"
        console.print(f"Cap space: [good]{money(space)}[/good]   "
                      f"Roster: {'[bad]' if full else ''}{len(team.roster)}/{ROSTER_MAX}"
                      f"{'[/bad] (full — waive someone to sign)' if full else ''}   "
                      f"MLE: {mle}   "
                      f"Filter: [accent]{pos_filter}[/accent]\n")
        console.print(_fa_table(world, team, shown, start))
        console.print(f"[dim]Showing {start + 1}-{start + len(shown)} of {len(fas)} free agents "
                      f"· page {page + 1}/{pages}[/dim]")

        opts = [("sign", "✍️   Sign a player (enter its #)"),
                ("ratings", "🔍  View a player's ratings (enter its #)")]
        if page < pages - 1:
            opts.append(("next", "▶  Next page"))
        if page > 0:
            opts.append(("prev", "◀  Previous page"))
        opts += [("filter", "🔎  Filter by position"),
                 ("waive", "🗑   Waive a player (free a roster spot)"),
                 ("back", "← Back")]
        action = choose("", opts)
        if action == "sign":
            n = ask_int("Player # to sign", default=0)
            if 1 <= n <= len(shown):
                _attempt_sign(world, team, shown[n - 1])
        elif action == "ratings":
            n = ask_int("Player # to scout", default=0)
            if 1 <= n <= len(shown):
                clear()
                header(world)
                console.print(player_card(world, shown[n - 1]))
                pause()
        elif action == "next":
            page += 1
        elif action == "prev":
            page -= 1
        elif action == "filter":
            choice = choose("Show which position?",
                            [("All", "All positions")] + [(p, p) for p in POSITIONS])
            pos_filter = choice or pos_filter
            page = 0
        elif action == "waive":
            _waive(world, team)
        else:
            return


def _fa_table(world: World, team, players, start: int) -> Table:
    table = Table(title="Free Agents", title_style="title", header_style="label")
    table.add_column("#", justify="right")
    for col in ("Name", "Pos", "Age", "OVR", "POT"):
        table.add_column(col, justify="right" if col in ("Age", "OVR", "POT") else "left")
    table.add_column("Asking", justify="right")
    table.add_column("Sign?", justify="left")
    for i, p in enumerate(players, start=1):
        salary = cap.market_salary(p)
        ok, _ = cap.can_sign(world, team, salary)
        pos = p.position + (f"/{p.secondary_position}" if p.secondary_position else "")
        table.add_row(str(i), p.name, pos, str(p.age),
                      f"[{ovr_style(p.overall)}]{p.overall}[/]", str(p.scouted_potential()),
                      money(salary), "[good]✓[/good]" if ok else "[bad]✗[/bad]")
    return table


def _attempt_sign(world: World, team, player) -> None:
    salary, years = freeagency.offer_for(world, team, player)
    console.print(f"Offer to [accent]{player.name}[/accent]: "
                  f"[money]{money(salary)}[/money] × {years}y")
    if not confirm("Submit this offer?", default=True):
        return
    ok, reason = freeagency.sign_free_agent(world, team, player.pid, salary, years)
    if ok:
        console.print(f"[good]{player.name} signs with {team.abbrev}![/good] [dim]({reason})[/dim]")
    else:
        console.print(f"[bad]Cannot sign:[/bad] {reason}")
    pause()


def _waive(world: World, team) -> None:
    players = sorted(roster_players(team, world.players), key=lambda p: p.overall)
    opts = [(str(p.pid),
             f"{p.name} [dim]{p.position} · OVR {p.overall} · "
             f"{money(p.contract.current_salary)}[/dim]") for p in players]
    key = choose("Waive which player?", opts, allow_back=True)
    if key is None:
        return
    player = world.players[int(key)]
    if confirm(f"Waive {player.name}? (dead money is ignored)", default=False):
        world.release_player(int(key))
        auto_set_lineup(team, world.players)
        console.print(f"[warn]{player.name} waived.[/warn]")
        pause()
