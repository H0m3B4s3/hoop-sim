"""Interactive draft screen: the user picks on the clock; the AI auto-picks otherwise."""
from __future__ import annotations

from typing import List, Tuple

from rich.panel import Panel
from rich.table import Table

from hoopsim.models.world import World
from hoopsim.systems import draft_system as D
from hoopsim.systems import scouting as SC
from hoopsim.systems import trades
from hoopsim.ui.console import choose, clear, console, pause
from hoopsim.ui.theme import ovr_style
from hoopsim.ui.widgets import header

_BOARD = 14


def draft_screen(world: World) -> None:
    dc = world.draft_class
    if dc is None or dc.complete or dc.year != world.season_year:
        dc = D.setup_draft(world)

    recent: List[Tuple[int, int, int]] = []   # (pick_no, tid, pid) since user's last pick
    user_picks: List[Tuple[int, int]] = []     # (pick_no, pid)

    while not dc.complete:
        tid = dc.team_on_clock()
        if tid == world.user_team_id:
            _user_pick(world, dc, recent, user_picks)
            recent = []
        else:
            pick_no = dc.current_pick
            pid = D.ai_pick(world)
            recent.append((pick_no, tid, pid))

    D.undrafted_to_free_agents(world)
    _draft_recap(world, user_picks)


def _board_table(world: World, dc) -> Table:
    table = Table(title="Big Board — Best Available", title_style="title", header_style="label")
    table.add_column("Sel", justify="right")
    for col in ("Prospect", "Pos", "Age", "OVR", "Pot", "PPG", "RPG", "APG"):
        table.add_column(col, justify="left" if col in ("Prospect", "Pos") else "right")
    remaining = sorted(dc.remaining_prospects(),
                       key=lambda pid: D.prospect_rank(world.players[pid]), reverse=True)[:_BOARD]
    for i, pid in enumerate(remaining, start=1):
        p = world.players[pid]
        s = p.pre_draft or {}
        v = SC.pot_view(p)
        pot = f"[label]{v.grade}[/label] [dim]{SC.pot_band_str(p)}[/dim]"
        table.add_row(str(i), f"{p.name} [dim]{p.archetype}[/dim]", p.position, str(p.age),
                      f"[{ovr_style(p.overall)}]{p.overall}[/]", pot,
                      str(s.get("ppg", "-")), str(s.get("rpg", "-")), str(s.get("apg", "-")))
    return table


def _user_pick(world: World, dc, recent, user_picks) -> None:
    clear()
    header(world)
    if recent:
        lines = []
        for pick_no, tid, pid in recent:
            t, p = world.teams[tid], world.players[pid]
            lines.append(f"  #{pick_no} [{t.color}]{t.abbrev}[/] select {p.name} "
                         f"[dim]{p.position} OVR {p.overall}[/dim]")
        console.print(Panel("\n".join(lines), title="[dim]Picks since your last selection[/dim]",
                            border_style="muted"))
    console.print(f"[accent]You are on the clock — pick #{dc.current_pick}[/accent]")
    console.print(_board_table(world, dc))

    remaining = sorted(dc.remaining_prospects(),
                       key=lambda pid: D.prospect_rank(world.players[pid]), reverse=True)[:_BOARD]
    options = [(str(pid),
                f"{world.players[pid].name} [dim]{world.players[pid].position} · "
                f"OVR {world.players[pid].overall} · {SC.pot_display(world.players[pid])}"
                f"[/dim]") for pid in remaining]
    options.append(("auto", "[dim]Auto-pick best available[/dim]"))
    cur_year = dc.year
    if world.user_team is not None and any(
            pk.year > cur_year for pk in world.picks_owned_by(world.user_team_id)):
        options.append(("shop", "[accent]Shop your future picks…[/accent]"))
    key = choose("Make your selection", options)
    while key == "shop":
        _shop_picks(world)
        clear()
        header(world)
        console.print(f"[accent]You are on the clock — pick #{dc.current_pick}[/accent]")
        console.print(_board_table(world, dc))
        key = choose("Make your selection", options)
    pid = D.best_available(world) if key == "auto" else int(key)
    pick_no = dc.current_pick
    D.make_pick(world, pid)
    user_picks.append((pick_no, pid))
    p = world.players[pid]
    console.print(Panel(f"[good]With pick #{pick_no}, you select {p.name}[/good]\n"
                        f"[dim]{p.position} · {p.archetype} · OVR {p.overall} · "
                        f"POT {SC.pot_display(p)}[/dim]", border_style="good"))
    pause()


def _shop_picks(world: World) -> None:
    """Let the user shop a draft pick for offers without leaving the draft room."""
    user = world.user_team
    cur = world.draft_class.year if world.draft_class else world.season_year
    picks = sorted((pk for pk in world.picks_owned_by(user.tid) if pk.year > cur),
                   key=lambda pk: (pk.year, pk.round))
    if not picks:
        console.print("[dim]You have no future picks to shop.[/dim]")
        pause()
        return
    while True:
        clear()
        header(world)
        from hoopsim.systems import cap
        opts = [(repr(pk.key),
                 f"{pk.year} {'1st' if pk.round == 1 else '2nd'}"
                 + (f" [dim](via {world.teams[pk.original_tid].abbrev})[/dim]"
                    if pk.original_tid != user.tid else "")
                 + f" [dim]· value {cap.pick_value(world, pk):.0f}[/dim]")
                for pk in picks]
        opts.append(("done", "[dim]Back to the board[/dim]"))
        key = choose("Which pick do you want to shop?", opts)
        if key == "done":
            return
        pick = next(pk for pk in picks if repr(pk.key) == key)
        offers = trades.solicit_pick_offers(world, pick.key)
        if not offers:
            console.print("[warn]No team made an offer for that pick.[/warn]")
            pause()
            continue
        oopts = []
        for idx, so in enumerate(offers):
            t = world.teams[so.offer.b]
            gives = [world.players[pid].name for pid in so.offer.b_sends]
            gives += [f"{world.find_pick(*k).year} "
                      f"{'1st' if k[1] == 1 else '2nd'}" for k in so.offer.b_picks]
            oopts.append((str(idx), f"[{t.color}]{t.abbrev}[/] gives "
                          + (", ".join(gives) or "—")))
        oopts.append(("cancel", "[dim]Cancel[/dim]"))
        sel = choose("Accept an offer?", oopts)
        if sel == "cancel":
            continue
        offer = offers[int(sel)].offer
        legal, why = trades.validate_trade(world, offer)
        if not legal:
            console.print(f"[bad]{why}[/bad]")
            pause()
            continue
        trades.execute_trade(world, offer)
        console.print("[good]Trade completed.[/good]")
        pause()
        return


def _draft_recap(world: World, user_picks) -> None:
    clear()
    header(world)
    if not user_picks:
        console.print("[dim]Your team had no draft picks.[/dim]")
        pause()
        return
    table = Table(title="Your Draft Class", title_style="title", header_style="label")
    table.add_column("Pick", justify="right")
    for col in ("Player", "Pos", "Age", "OVR", "Pot"):
        table.add_column(col, justify="right" if col in ("Age", "OVR", "Pot") else "left")
    for pick_no, pid in user_picks:
        p = world.players[pid]
        table.add_row(f"#{pick_no}", p.name, p.position, str(p.age),
                      f"[{ovr_style(p.overall)}]{p.overall}[/]", SC.pot_display(p))
    console.print(table)
    pause()
