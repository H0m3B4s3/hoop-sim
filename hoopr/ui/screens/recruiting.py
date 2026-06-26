"""Recruiting screen: court high-school prospects, then resolve Signing Day."""
from __future__ import annotations

from typing import Dict

from rich.panel import Panel
from rich.table import Table

from hoopr.gen.collegegen import star_rating
from hoopr.models.world import World
from hoopr.systems import collegefin, recruiting
from hoopr.ui.console import ask_int, choose, clear, console, pause
from hoopr.ui.theme import ovr_style
from hoopr.ui.widgets import header, money

_BOARD = 20


def recruiting_screen(world: World) -> Dict[int, object]:
    """Let the user make offers, then resolve recruiting. Returns the resolve summary."""
    team = world.user_team
    nil = world.college_economy == "nil"
    offers: Dict[int, object] = {}
    while True:
        clear()
        header(world)
        _intro(world, team, nil)
        console.print(_board(world, team, offers, nil))
        action = choose("", [
            ("offer", "🎯 Make an offer to a recruit"),
            ("remove", "✖  Withdraw an offer"),
            ("sign", "📝 Signing Day — resolve recruiting"),
        ])
        if action == "offer":
            _make_offer(world, team, offers, nil)
        elif action == "remove":
            pid = _pick_recruit(world, list(offers.keys()), "Withdraw offer to whom?")
            if pid is not None:
                offers.pop(pid, None)
        elif action == "sign":
            return _sign_day(world, offers)


def _intro(world: World, team, nil: bool) -> None:
    if nil:
        console.print(f"NIL collective: [money]{money(collegefin.nil_available(world, team))}[/money]"
                      f" available of {money(team.nil_budget)}   ·   open spots: "
                      f"{collegefin.scholarships_open(team)}\n")
    else:
        console.print(f"Scholarships open: [accent]{collegefin.scholarships_open(team)}[/accent]"
                      f"   ·   Recruit via prestige ({'★' * team.prestige}) + active interest\n")


def _board(world: World, team, offers, nil: bool) -> Table:
    table = Table(title="Recruiting Board", title_style="title", header_style="label")
    table.add_column("#", justify="right")
    for col in ("Recruit", "Pos", "Stars", "OVR", "POT"):
        table.add_column(col, justify="right" if col in ("OVR", "POT", "Stars") else "left")
    table.add_column("Your offer", justify="right")
    recruits = sorted(world.recruit_players(), key=lambda p: p.scouted_potential(),
                      reverse=True)[:_BOARD]
    for i, p in enumerate(recruits, start=1):
        offer = offers.get(p.pid)
        if offer is True:
            offer_txt = "[good]Scholarship[/good]"
        elif isinstance(offer, int):
            offer_txt = f"[money]{money(offer)}[/money]"
        else:
            offer_txt = "[dim]—[/dim]"
        table.add_row(str(i), p.name, p.position, "★" * star_rating(p),
                      f"[{ovr_style(p.overall)}]{p.overall}[/]", str(p.scouted_potential()),
                      offer_txt)
    return table


def _ranked_recruits(world: World):
    return sorted(world.recruit_players(), key=lambda p: p.scouted_potential(), reverse=True)[:_BOARD]


def _pick_recruit(world: World, pids, prompt: str):
    pool = [p for p in _ranked_recruits(world) if not pids or p.pid in pids]
    if not pool:
        console.print("[dim]No recruits.[/dim]")
        pause()
        return None
    opts = [(str(p.pid), f"{p.name} [dim]{p.position} · {'★' * star_rating(p)} · "
             f"POT {p.scouted_potential()}[/dim]") for p in pool]
    key = choose(prompt, opts, allow_back=True)
    return int(key) if key is not None else None


def _make_offer(world: World, team, offers, nil: bool) -> None:
    pid = _pick_recruit(world, None, "Offer to which recruit?")
    if pid is None:
        return
    if nil:
        avail = collegefin.nil_available(world, team)
        console.print(f"[dim]Available NIL: {money(avail)}[/dim]")
        amount = ask_int("NIL offer ($, e.g. 500000)", default=250_000)
        if amount <= 0:
            offers.pop(pid, None)
        else:
            offers[pid] = int(amount)
    else:
        offers[pid] = True
        console.print("[good]Offer extended.[/good]")


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
