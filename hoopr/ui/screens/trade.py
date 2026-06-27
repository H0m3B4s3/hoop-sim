"""Trade screen: build a package, preview legality, and get the AI team's verdict."""
from __future__ import annotations

from typing import List, Optional

from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table

from hoopr.models.world import World
from hoopr.systems import cap
from hoopr.systems.trades import (TradeOffer, ai_evaluates, execute_trade,
                                  solicit_offers, team_trade_block,
                                  trade_deadline_passed, validate_trade)
from hoopr.ui.console import choose, clear, confirm, console, pause
from hoopr.ui.widgets import header, money, player_card


def trade_screen(world: World) -> None:
    if trade_deadline_passed(world):
        console.print("[bad]The trade deadline has passed.[/bad] "
                      "[dim]You can still waive players from Free Agency; trading reopens "
                      "next season.[/dim]")
        pause()
        return
    a = world.user_team
    b_tid = _choose_team(world)
    if b_tid is None:
        return
    a_sends: List[int] = []
    b_sends: List[int] = []
    a_picks: List[tuple] = []
    b_picks: List[tuple] = []
    while True:
        b = world.teams[b_tid]
        block = set(team_trade_block(world, b))
        clear()
        header(world)
        _render_block(world, b, block)
        _render_offer(world, a, b, a_sends, b_sends, a_picks, b_picks)
        offer = TradeOffer(a.tid, b.tid, list(a_sends), list(b_sends),
                           list(a_picks), list(b_picks))
        legal, reason = validate_trade(world, offer)
        style = "good" if legal else "warn"
        console.print(f"[{style}]{reason}[/{style}]\n")

        opts = [("add_send", "➕ Add a player to send")]
        if a_sends:
            opts.append(("rm_send", "➖ Remove a player you're sending"))
        if [p for p in world.picks_owned_by(a.tid) if p.key not in a_picks]:
            opts.append(("add_send_pick", "🎟️  Add a draft pick to send"))
        if a_picks:
            opts.append(("rm_send_pick", "➖ Remove a pick you're sending"))
        opts.append(("add_get", f"🎯 Add a player to request from {b.abbrev}"))
        if b_sends:
            opts.append(("rm_get", "➖ Remove a requested player"))
        if [p for p in world.picks_owned_by(b.tid) if p.key not in b_picks]:
            opts.append(("add_get_pick", f"🎟️  Request a pick from {b.abbrev}"))
        if b_picks:
            opts.append(("rm_get_pick", "➖ Remove a requested pick"))
        opts += [("inspect", "🔍 Scout a player's ratings"),
                 ("propose", "📨 Propose trade"),
                 ("solicit", "📣 Solicit offers for your players"),
                 ("team", "🔄 Different team"), ("back", "← Back")]
        action = choose("", opts)

        if action == "add_send":
            pid = _pick(world, [p for p in a.roster if p not in a_sends], "Send which player?")
            if pid is not None:
                a_sends.append(pid)
        elif action == "rm_send":
            pid = _pick(world, a_sends, "Remove which player?")
            if pid is not None:
                a_sends.remove(pid)
        elif action == "add_send_pick":
            key = _pick_draft_pick(world, a.tid, a_picks, "Send which pick?")
            if key is not None:
                a_picks.append(key)
        elif action == "rm_send_pick":
            key = _pick_draft_pick(world, a.tid, [], "Remove which pick?", only=a_picks)
            if key is not None:
                a_picks.remove(key)
        elif action == "add_get":
            pid = _pick(world, [p for p in b.roster if p not in b_sends], "Request which player?",
                        block=block)
            if pid is not None:
                b_sends.append(pid)
        elif action == "rm_get":
            pid = _pick(world, b_sends, "Remove which player?")
            if pid is not None:
                b_sends.remove(pid)
        elif action == "add_get_pick":
            key = _pick_draft_pick(world, b.tid, b_picks, f"Request which {b.abbrev} pick?")
            if key is not None:
                b_picks.append(key)
        elif action == "rm_get_pick":
            key = _pick_draft_pick(world, b.tid, [], "Remove which pick?", only=b_picks)
            if key is not None:
                b_picks.remove(key)
        elif action == "solicit":
            _solicit(world, a)
        elif action == "inspect":
            _inspect(world, a, b)
        elif action == "propose":
            _propose(world, TradeOffer(a.tid, b.tid, list(a_sends), list(b_sends),
                                       list(a_picks), list(b_picks)), b_tid)
            # if the trade executed, assets changed hands; drop any that moved
            a_sends = [p for p in a_sends if p in a.roster]
            b_sends = [p for p in b_sends if p in world.teams[b_tid].roster]
            a_picks = [k for k in a_picks if (pk := world.find_pick(*k)) and pk.owner_tid == a.tid]
            b_picks = [k for k in b_picks if (pk := world.find_pick(*k)) and pk.owner_tid == b.tid]
        elif action == "team":
            new_b = _choose_team(world)
            if new_b is not None:
                b_tid = new_b
                a_sends, b_sends, a_picks, b_picks = [], [], [], []
        elif action == "back" or action is None:
            return


def _pick_label(world: World, pick) -> str:
    rnd = {1: "1st", 2: "2nd"}.get(pick.round, f"R{pick.round}")
    via = (f" via {world.find_team(pick.original_tid).abbrev}"
           if pick.original_tid != pick.owner_tid else "")
    return f"{pick.year} {rnd}{via}"


def _pick_draft_pick(world: World, tid: int, exclude: List[tuple], prompt: str,
                     only: Optional[List[tuple]] = None) -> Optional[tuple]:
    """Choose one of a team's tradeable picks (``only`` restricts to that subset)."""
    from hoopr.systems import cap
    picks = world.picks_owned_by(tid)
    if only is not None:
        picks = [p for p in picks if p.key in only]
    picks = [p for p in picks if p.key not in exclude]
    if not picks:
        console.print("[dim]No eligible picks.[/dim]")
        pause()
        return None
    opts = [(str(i), f"🎟️  {_pick_label(world, p)} [dim]· val {cap.pick_value(world, p):.1f}[/dim]")
            for i, p in enumerate(picks)]
    key = choose(prompt, opts, allow_back=True)
    return picks[int(key)].key if key is not None else None


def _choose_team(world: World) -> Optional[int]:
    opts = [(str(t.tid), f"[{t.color}]{t.abbrev}[/] {t.full_name}")
            for t in sorted(world.team_list(), key=lambda t: t.full_name)
            if t.tid != world.user_team_id]
    key = choose("Trade with which team?", opts, allow_back=True)
    return int(key) if key is not None else None


def _pick(world: World, pids: List[int], prompt: str,
          block: Optional[set] = None) -> Optional[int]:
    if not pids:
        console.print("[dim]No eligible players.[/dim]")
        pause()
        return None
    block = block or set()
    players = sorted((world.players[pid] for pid in pids), key=lambda p: p.overall, reverse=True)
    opts = [(str(p.pid),
             f"{'[accent]✦[/accent] ' if p.pid in block else ''}{p.name} "
             f"[dim]{p.position} · OVR {p.overall} · {money(p.contract.current_salary)} "
             f"· val {cap.trade_value(p):.1f}[/dim]") for p in players]
    key = choose(prompt, opts, allow_back=True)
    return int(key) if key is not None else None


def _render_block(world: World, b, block: set) -> None:
    """Show the partner's shopping list — the aging vets they're dangling — above the deal."""
    if not block:
        return
    names = ", ".join(f"{world.players[pid].name} ([dim]{world.players[pid].position} "
                      f"{world.players[pid].overall}[/dim])"
                      for pid in sorted(block, key=lambda x: world.players[x].overall, reverse=True))
    console.print(f"[accent]✦ {b.abbrev} are shopping:[/accent] {names}\n")


def _solicit(world: World, a) -> None:
    """Shop your own players around the league and pick from the offers that come back."""
    shop: List[int] = []
    while True:
        clear()
        header(world)
        if shop:
            console.print(_side_table(world, a, shop, f"{a.abbrev} shopping"))
        opts = [("add", "➕ Add a player to shop")]
        if shop:
            opts += [("rm", "➖ Remove a player"), ("go", "📣 Get offers")]
        opts.append(("back", "← Back"))
        action = choose("", opts)
        if action == "add":
            pid = _pick(world, [p for p in a.roster if p not in shop], "Shop which player?")
            if pid is not None:
                shop.append(pid)
        elif action == "rm":
            pid = _pick(world, shop, "Remove which player?")
            if pid is not None:
                shop.remove(pid)
        elif action == "go":
            if _review_offers(world, a, shop):
                return        # a trade executed; the shopped players are gone
        elif action == "back" or action is None:
            return


def _offer_assets(world: World, offer) -> str:
    """Comma-joined names of the players and picks coming back to the user in an offer."""
    parts = [f"{world.players[pid].name} ([dim]{world.players[pid].position} "
             f"{world.players[pid].overall}[/dim])" for pid in offer.b_sends]
    parts += [f"🎟️  {_pick_label(world, pk)}"
              for k in offer.b_picks if (pk := world.find_pick(*k))]
    return ", ".join(parts)


def _review_offers(world: World, a, shop: List[int]) -> bool:
    """List solicited offers and let the user accept one. Returns True if a deal was made."""
    offers = solicit_offers(world, shop)
    if not offers:
        console.print("[dim]No team made an offer for that package.[/dim]")
        pause()
        return False
    while True:
        opts = []
        for i, so in enumerate(offers):
            b = world.teams[so.offer.b]
            opts.append((str(i), f"[{b.color}]{b.abbrev}[/]: {_offer_assets(world, so.offer)} "
                                 f"[dim](val {so.value:.1f})[/dim]"))
        key = choose("Accept which offer?", opts, allow_back=True)
        if key is None:
            return False
        so = offers[int(key)]
        b = world.teams[so.offer.b]
        console.print(Panel(f"[good]{b.full_name} offer[/good] for "
                            f"{', '.join(world.players[p].name for p in so.offer.a_sends)}:\n"
                            f"[dim]{_offer_assets(world, so.offer)}[/dim]", border_style="good"))
        if confirm("Accept this trade?", default=True):
            execute_trade(world, so.offer)
            console.print("[good]Trade completed.[/good]")
            pause()
            return True


def _inspect(world: World, a, b) -> None:
    """Scout the full ratings of any player on either roster without leaving the deal."""
    team_key = choose("Scout a player from which team?",
                      [(str(a.tid), f"[{a.color}]{a.abbrev}[/] (yours)"),
                       (str(b.tid), f"[{b.color}]{b.abbrev}[/]")], allow_back=True)
    if team_key is None:
        return
    team = world.teams[int(team_key)]
    pid = _pick(world, list(team.roster), f"Scout which {team.abbrev} player?")
    if pid is None:
        return
    clear()
    header(world)
    console.print(player_card(world, world.players[pid]))
    pause()


def _side_table(world: World, team, pids: List[int], title: str,
                picks: Optional[List[tuple]] = None) -> Table:
    table = Table(title=title, title_style="title", header_style="label", expand=True)
    table.add_column("Asset")
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
    for key in (picks or []):
        pick = world.find_pick(*key)
        if pick is None:
            continue
        val = cap.pick_value(world, pick)
        total_val += val
        table.add_row(f"🎟️  {_pick_label(world, pick)}", "", "", f"{val:.1f}")
    table.add_section()
    table.add_row("[label]Total[/label]", "", money(total_sal), f"{total_val:.1f}")
    return table


def _render_offer(world, a, b, a_sends, b_sends, a_picks=None, b_picks=None) -> None:
    left = _side_table(world, a, a_sends, f"{a.abbrev} sends", a_picks)
    right = _side_table(world, b, b_sends, f"{b.abbrev} sends", b_picks)
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
