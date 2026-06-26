"""Trade screen: build a package, preview legality, and get the AI team's verdict."""
from __future__ import annotations

from typing import List, Optional

from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table

from hoopr.models.world import World
from hoopr.systems import cap
from hoopr.systems.trades import TradeOffer, ai_evaluates, execute_trade, validate_trade
from hoopr.ui.console import choose, clear, confirm, console, pause
from hoopr.ui.widgets import header, money


def trade_screen(world: World) -> None:
    a = world.user_team
    b_tid = _choose_team(world)
    if b_tid is None:
        return
    a_sends: List[int] = []
    b_sends: List[int] = []
    while True:
        b = world.teams[b_tid]
        clear()
        header(world)
        _render_offer(world, a, b, a_sends, b_sends)
        offer = TradeOffer(a.tid, b.tid, list(a_sends), list(b_sends))
        legal, reason = validate_trade(world, offer)
        style = "good" if legal else "warn"
        console.print(f"[{style}]{reason}[/{style}]\n")

        opts = [("add_send", "➕ Add a player to send")]
        if a_sends:
            opts.append(("rm_send", "➖ Remove a player you're sending"))
        opts.append(("add_get", f"🎯 Add a player to request from {b.abbrev}"))
        if b_sends:
            opts.append(("rm_get", "➖ Remove a requested player"))
        opts += [("propose", "📨 Propose trade"), ("team", "🔄 Different team"),
                 ("back", "← Back")]
        action = choose("", opts)

        if action == "add_send":
            pid = _pick(world, [p for p in a.roster if p not in a_sends], "Send which player?")
            if pid is not None:
                a_sends.append(pid)
        elif action == "rm_send":
            pid = _pick(world, a_sends, "Remove which player?")
            if pid is not None:
                a_sends.remove(pid)
        elif action == "add_get":
            pid = _pick(world, [p for p in b.roster if p not in b_sends], "Request which player?")
            if pid is not None:
                b_sends.append(pid)
        elif action == "rm_get":
            pid = _pick(world, b_sends, "Remove which player?")
            if pid is not None:
                b_sends.remove(pid)
        elif action == "propose":
            _propose(world, TradeOffer(a.tid, b.tid, list(a_sends), list(b_sends)), b_tid)
            # if the trade executed, players changed teams; drop any that moved
            a_sends = [p for p in a_sends if p in a.roster]
            b_sends = [p for p in b_sends if p in world.teams[b_tid].roster]
        elif action == "team":
            new_b = _choose_team(world)
            if new_b is not None:
                b_tid = new_b
                a_sends, b_sends = [], []
        elif action == "back" or action is None:
            return


def _choose_team(world: World) -> Optional[int]:
    opts = [(str(t.tid), f"[{t.color}]{t.abbrev}[/] {t.full_name}")
            for t in sorted(world.team_list(), key=lambda t: t.full_name)
            if t.tid != world.user_team_id]
    key = choose("Trade with which team?", opts, allow_back=True)
    return int(key) if key is not None else None


def _pick(world: World, pids: List[int], prompt: str) -> Optional[int]:
    if not pids:
        console.print("[dim]No eligible players.[/dim]")
        pause()
        return None
    players = sorted((world.players[pid] for pid in pids), key=lambda p: p.overall, reverse=True)
    opts = [(str(p.pid),
             f"{p.name} [dim]{p.position} · OVR {p.overall} · {money(p.contract.current_salary)} "
             f"· val {cap.trade_value(p):.1f}[/dim]") for p in players]
    key = choose(prompt, opts, allow_back=True)
    return int(key) if key is not None else None


def _side_table(world: World, team, pids: List[int], title: str) -> Table:
    table = Table(title=title, title_style="title", header_style="label", expand=True)
    table.add_column("Player")
    table.add_column("OVR", justify="right")
    table.add_column("Salary", justify="right")
    table.add_column("Val", justify="right")
    total_sal = 0
    total_val = 0.0
    for pid in pids:
        p = world.players[pid]
        total_sal += p.contract.current_salary
        total_val += cap.trade_value(p)
        table.add_row(p.name, str(p.overall), money(p.contract.current_salary),
                      f"{cap.trade_value(p):.1f}")
    table.add_section()
    table.add_row("[label]Total[/label]", "", money(total_sal), f"{total_val:.1f}")
    return table


def _render_offer(world, a, b, a_sends, b_sends) -> None:
    left = _side_table(world, a, a_sends, f"{a.abbrev} sends")
    right = _side_table(world, b, b_sends, f"{b.abbrev} sends")
    console.print(Columns([left, right], padding=(0, 3), equal=True, expand=True))


def _propose(world: World, offer: TradeOffer, b_tid: int) -> None:
    legal, reason = validate_trade(world, offer)
    if not legal:
        console.print(f"[bad]Illegal trade:[/bad] {reason}")
        pause()
        return
    accepts, verdict = ai_evaluates(world, offer, b_tid)
    b = world.teams[b_tid]
    if not accepts:
        console.print(Panel(f"[bad]{b.full_name} reject the offer.[/bad]\n[dim]\"{verdict}\"[/dim]",
                            border_style="bad"))
        pause()
        return
    console.print(Panel(f"[good]{b.full_name} accept![/good]\n[dim]\"{verdict}\"[/dim]",
                        border_style="good"))
    if confirm("Finalize this trade?", default=True):
        execute_trade(world, offer)
        console.print("[good]Trade completed.[/good]")
    pause()
