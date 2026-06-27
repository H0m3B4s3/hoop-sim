"""Console-driven end-of-game coaching.

:class:`LiveCoach` is the interactive implementation of :class:`hoopr.sim.coach.Coach`. The engine
hands it a :class:`~hoopr.sim.coach.CoachView` before each of the user team's crunch-time
possessions; this renders the situation, lets the user sub, call timeouts, set tempo, or order a
deliberate foul, and returns the resulting :class:`~hoopr.sim.coach.CoachOrders`. After the
possession resolves the engine calls :meth:`narrate` to print what happened.
"""
from __future__ import annotations

from typing import List, Optional

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from hoopsim.models.world import World
from hoopsim.sim.coach import Coach, CoachOrders, CoachView, PlayerView
from hoopsim.ui.console import choose, console

_TEMPO_LABEL = {
    "normal": "Run the offense (normal)",
    "bleed": "Bleed the clock (milk the shot clock)",
    "hold": "Hold for the last shot",
    "quick3": "Quick 3 (get aggressive)",
}
_TEMPO_ORDER = ("normal", "bleed", "hold", "quick3")
_FOUL_LABEL = {
    "auto": "Foul: Auto (let the team decide)",
    "foul": "Foul now (send them to the line)",
    "no": "Don't foul (play it straight)",
}


def _clock(secs: float) -> str:
    secs = max(0, int(secs))
    m, s = divmod(secs, 60)
    return f"{m}:{s:02d}"


def _fatigue_tag(f: float) -> str:
    if f >= 70:
        return "[bad]gassed[/bad]"
    if f >= 45:
        return "[warn]tiring[/warn]"
    return "[dim]fresh[/dim]"


class LiveCoach(Coach):
    def __init__(self, world: World, user_tid: int, home_tid: int, away_tid: int) -> None:
        self.world = world
        self.user_tid = user_tid
        self.team = world.teams[user_tid]
        self.home = world.find_team(home_tid)
        self.away = world.find_team(away_tid)
        self.engaged = False    # set once the user has been given live control

    # -- engine entry points ------------------------------------------------
    def decide(self, view: CoachView) -> CoachOrders:
        self.engaged = True
        orders = CoachOrders()
        lineup: List[int] = [p.pid for p in view.on_court]

        if view.first_engagement:
            self._banner(view)

        while True:
            self._render(view, orders, lineup)
            options = self._menu(view, orders, lineup)
            action = choose("", options)
            if action == "go":
                break
            elif action == "tempo":
                orders.tempo = _TEMPO_ORDER[(_TEMPO_ORDER.index(orders.tempo) + 1) % len(_TEMPO_ORDER)]
            elif action == "foul":
                order = ("auto", "foul", "no")
                orders.defensive_foul = order[(order.index(orders.defensive_foul) + 1) % len(order)]
            elif action == "timeout":
                orders.timeout = not orders.timeout
            elif action == "sub":
                lineup = self._substitute(view, lineup)

        if lineup != [p.pid for p in view.on_court]:
            orders.lineup = lineup
        return orders

    def narrate(self, events) -> None:
        for e in events:
            team = self.world.find_team(e.tid) if e.tid is not None else None
            tag = f"[{team.color}]{team.abbrev}[/]" if team else "   "
            score = f"[dim]{self.away.abbrev} {e.away_score}-{e.home_score} {self.home.abbrev}[/dim]"
            console.print(f"   {tag}  {e.text}   {score}")

    # -- rendering ----------------------------------------------------------
    def _banner(self, view: CoachView) -> None:
        console.print()
        console.rule(f"[title]CRUNCH TIME — you're coaching the finish[/title]", style="accent")

    def _render(self, view: CoachView, orders: CoachOrders, lineup: List[int]) -> None:
        console.print()
        lead = view.user_lead
        if lead > 0:
            margin = f"[good]up {lead}[/good]"
        elif lead < 0:
            margin = f"[bad]down {-lead}[/bad]"
        else:
            margin = "[warn]tied[/warn]"
        side = "offense — you have the ball" if view.user_on_offense else "defense"
        head = (f"[title]{view.period_label.title()} {view.quarter}  {_clock(view.clock)}[/title]"
                f"   {self.team.abbrev} {margin}   ([dim]{side}[/dim])")
        console.print(Panel.fit(head, border_style=self.team.color))

        bonus = []
        if view.user_in_bonus:
            bonus.append("[good]you're in the bonus[/good]")
        if view.opp_in_bonus:
            bonus.append("[bad]they're in the bonus[/bad]")
        console.print(f"  Timeouts — [bold]{self.team.abbrev} {view.user_timeouts}[/bold] / "
                      f"opp {view.opp_timeouts}"
                      + (("    " + " · ".join(bonus)) if bonus else ""))

        tbl = Table(show_header=True, header_style="muted", box=None, pad_edge=False)
        tbl.add_column("On the floor")
        tbl.add_column("Pos", justify="center")
        tbl.add_column("OVR", justify="right")
        tbl.add_column("PF", justify="right")
        tbl.add_column("", justify="left")
        by_pid = {p.pid: p for p in view.on_court + view.bench}
        for pid in lineup:
            p = by_pid.get(pid)
            if p is None:
                continue
            pf = f"[bad]{p.fouls}[/bad]" if p.fouls >= 5 else str(p.fouls)
            tbl.add_row(p.name, p.pos, str(p.overall), pf, _fatigue_tag(p.fatigue))
        console.print(tbl)

    def _menu(self, view: CoachView, orders: CoachOrders, lineup: List[int]):
        opts = []
        if view.user_on_offense:
            opts.append(("tempo", f"Tempo → [accent]{_TEMPO_LABEL[orders.tempo]}[/accent]"))
        else:
            opts.append(("foul", f"Defense → [accent]{_FOUL_LABEL[orders.defensive_foul]}[/accent]"))
        if view.user_timeouts > 0:
            mark = "[good]✓[/good] " if orders.timeout else ""
            opts.append(("timeout", f"{mark}Call timeout (advance the ball, rest legs)"))
        elif orders.timeout:
            orders.timeout = False
        opts.append(("sub", "Substitute"))
        changed = " [dim](changed)[/dim]" if lineup != [p.pid for p in view.on_court] else ""
        opts.append(("go", f"[bold]▶  Run the possession[/bold]{changed}"))
        return opts

    # -- substitutions ------------------------------------------------------
    def _substitute(self, view: CoachView, lineup: List[int]) -> List[int]:
        by_pid = {p.pid: p for p in view.on_court + view.bench}
        bench_pool = [p for p in view.bench if p.pid not in lineup]
        while True:
            console.print()
            out_opts = [(str(pid), self._sub_label(by_pid[pid])) for pid in lineup]
            out_opts.append(("__done__", "[dim]Done subbing[/dim]"))
            console.print(Text("Sub OUT:", style="title"))
            out_key = choose("", out_opts)
            if out_key == "__done__" or out_key is None:
                return lineup
            if not bench_pool:
                console.print("[warn]No available bench players to bring in.[/warn]")
                return lineup
            in_opts = [(str(p.pid), self._sub_label(p)) for p in bench_pool]
            console.print(Text("Bring IN:", style="title"))
            in_key = choose("", in_opts)
            if in_key is None:
                continue
            out_pid, in_pid = int(out_key), int(in_key)
            lineup = [in_pid if pid == out_pid else pid for pid in lineup]
            bench_pool = [p for p in view.bench if p.pid not in lineup]

    @staticmethod
    def _sub_label(p: PlayerView) -> str:
        pf = f" · [bad]{p.fouls} PF[/bad]" if p.fouls >= 5 else (f" · {p.fouls} PF" if p.fouls else "")
        mins = f" · {int(p.secs // 60)}m"
        return f"{p.name} ({p.pos}, {p.overall}){pf}{mins} {_fatigue_tag(p.fatigue)}"
