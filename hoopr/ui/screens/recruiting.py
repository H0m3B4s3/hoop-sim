"""Recruiting screen: court high-school prospects, then resolve Signing Day."""
from __future__ import annotations

from typing import Dict, List

from rich.panel import Panel
from rich.table import Table

from hoopr.gen.collegegen import star_rating
from hoopr.models.attributes import POSITIONS
from hoopr.models.team import roster_players
from hoopr.models.world import World
from hoopr.systems import collegefin, recruiting
from hoopr.ui.console import ask_int, choose, clear, console, pause
from hoopr.ui.theme import ovr_style
from hoopr.ui.widgets import class_label, header, money, player_card

_PAGE = 18


def recruiting_screen(world: World) -> Dict[int, object]:
    """Let the user make offers, then resolve recruiting. Returns the resolve summary."""
    team = world.user_team
    nil = world.college_economy == "nil"
    offers: Dict[int, object] = {}
    pos_filter = "All"
    page = 0
    while True:
        recruits = sorted(world.recruit_players(), key=lambda p: p.scouted_potential(),
                          reverse=True)
        if pos_filter != "All":
            recruits = [p for p in recruits
                        if p.position == pos_filter or p.secondary_position == pos_filter]
        pages = max(1, (len(recruits) + _PAGE - 1) // _PAGE)
        page = max(0, min(page, pages - 1))
        start = page * _PAGE
        shown = recruits[start:start + _PAGE]

        clear()
        header(world)
        _intro(world, team, nil)
        console.print(f"Filter: [accent]{pos_filter}[/accent]\n")
        console.print(_board(shown, offers, start))
        console.print(f"[dim]Showing {start + 1}-{start + len(shown)} of {len(recruits)} recruits "
                      f"· page {page + 1}/{pages}[/dim]")

        opts = [("offer", "🎯 Make an offer (enter its #)"),
                ("ratings", "🔍  Scout a recruit's ratings (enter its #)")]
        if page < pages - 1:
            opts.append(("next", "▶  Next page"))
        if page > 0:
            opts.append(("prev", "◀  Previous page"))
        opts += [("filter", "🔎  Filter by position"),
                 ("depth", "📋  View your depth chart"),
                 ("remove", "✖  Withdraw an offer"),
                 ("sign", "📝 Signing Day — resolve recruiting")]
        action = choose("", opts)
        if action == "offer":
            n = ask_int("Recruit # to offer", default=0)
            if 1 <= n <= len(shown):
                _make_offer(world, team, offers, nil, shown[n - 1])
        elif action == "ratings":
            n = ask_int("Recruit # to scout", default=0)
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
        elif action == "depth":
            _show_depth_chart(world, team)
        elif action == "remove":
            pid = _pick_offered(world, offers, "Withdraw offer to whom?")
            if pid is not None:
                offers.pop(pid, None)
        elif action == "sign":
            return _sign_day(world, offers)


def _intro(world: World, team, nil: bool) -> None:
    if nil:
        console.print(f"NIL collective: [money]{money(collegefin.nil_available(world, team))}[/money]"
                      f" available of {money(team.nil_budget)}   ·   open spots: "
                      f"{collegefin.scholarships_open(team)}")
    else:
        console.print(f"Scholarships open: [accent]{collegefin.scholarships_open(team)}[/accent]"
                      f"   ·   Recruit via prestige ({'★' * team.prestige}) + active interest")


def _board(recruits, offers, start: int) -> Table:
    table = Table(title="Recruiting Board", title_style="title", header_style="label")
    table.add_column("#", justify="right")
    for col in ("Recruit", "Pos", "Stars", "OVR", "POT"):
        table.add_column(col, justify="right" if col in ("OVR", "POT", "Stars") else "left")
    table.add_column("Your offer", justify="right")
    for i, p in enumerate(recruits, start=1):
        offer = offers.get(p.pid)
        if offer is True:
            offer_txt = "[good]Scholarship[/good]"
        elif isinstance(offer, int):
            offer_txt = f"[money]{money(offer)}[/money]"
        else:
            offer_txt = "[dim]—[/dim]"
        pos = p.position + (f"/{p.secondary_position}" if p.secondary_position else "")
        table.add_row(str(i), p.name, pos, "★" * star_rating(p),
                      f"[{ovr_style(p.overall)}]{p.overall}[/]", str(p.scouted_potential()),
                      offer_txt)
    return table


def _pick_offered(world: World, offers, prompt: str):
    pool = [world.players[pid] for pid in offers if pid in world.players]
    if not pool:
        console.print("[dim]No active offers.[/dim]")
        pause()
        return None
    opts = [(str(p.pid), f"{p.name} [dim]{p.position} · {'★' * star_rating(p)} · "
             f"POT {p.scouted_potential()}[/dim]") for p in pool]
    key = choose(prompt, opts, allow_back=True)
    return int(key) if key is not None else None


def _make_offer(world: World, team, offers, nil: bool, recruit) -> None:
    if nil:
        avail = collegefin.nil_available(world, team)
        console.print(f"[dim]NIL offer to {recruit.name} — available: {money(avail)}[/dim]")
        amount = ask_int("NIL offer ($, e.g. 500000)", default=250_000)
        if amount <= 0:
            offers.pop(recruit.pid, None)
        else:
            offers[recruit.pid] = int(amount)
    else:
        offers[recruit.pid] = True
        console.print(f"[good]Scholarship offer extended to {recruit.name}.[/good]")


def _show_depth_chart(world: World, team) -> None:
    """Show the user's roster grouped by position so they can see where they're thin."""
    clear()
    header(world)
    by_pos: Dict[str, List] = {pos: [] for pos in POSITIONS}
    for p in roster_players(team, world.players):
        by_pos[p.position].append(p)
    table = Table(title="Your Depth Chart", title_style="title", header_style="label")
    table.add_column("Pos", justify="left")
    table.add_column("#", justify="right")
    table.add_column("Players (OVR · class — graduating ★)", justify="left")
    for pos in POSITIONS:
        players = sorted(by_pos[pos], key=lambda p: p.overall, reverse=True)
        if players:
            cells = []
            for p in players:
                grad = " ★" if p.class_year >= 4 else ""
                cells.append(f"{p.last_name} [{ovr_style(p.overall)}]{p.overall}[/]"
                             f" [dim]{class_label(p.class_year)}[/dim]{grad}")
            body = ", ".join(cells)
        else:
            body = "[bad]— none —[/bad]"
        count_style = "bad" if len(players) < 2 else ""
        count = f"[{count_style}]{len(players)}[/{count_style}]" if count_style else str(len(players))
        table.add_row(pos, count, body)
    console.print(table)
    console.print("[dim]★ = senior (graduating after this season). Thin spots (<2) are flagged "
                  "in red — recruit there.[/dim]")
    pause()


def _sign_day(world: World, offers) -> dict:
    summary = recruiting.resolve_recruiting(world, offers)
    clear()
    header(world)
    signed = summary["user_signings"]
    if signed:
        table = Table(title="Your Signing Class", title_style="title", header_style="label")
        for col in ("Recruit", "Pos", "Stars", "OVR", "POT"):
            table.add_column(col, justify="right" if col in ("OVR", "POT", "Stars") else "left")
        for pid in signed:
            p = world.players[pid]
            table.add_row(p.name, p.position, "★" * star_rating(p), str(p.overall),
                          str(p.scouted_potential()))
        console.print(table)
        console.print(f"[good]Signed {len(signed)} recruit(s)![/good]")
    else:
        console.print(Panel("[warn]You didn't land any recruits this cycle.[/warn]\n"
                            "[dim]Higher-prestige programs and bigger NIL offers win battles for "
                            "top talent.[/dim]", border_style="warn"))
    pause()
    return summary
