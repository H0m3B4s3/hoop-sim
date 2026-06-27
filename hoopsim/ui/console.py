"""Shared rich Console and small input/output helpers."""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.text import Text

from hoopsim.ui.theme import HOOPSIM_THEME

console = Console(theme=HOOPSIM_THEME)


def clear() -> None:
    console.clear()


def pause(message: str = "Press Enter to continue") -> None:
    console.print(f"[dim]{message}…[/dim]", end="")
    try:
        input()
    except EOFError:
        console.print()


def rule(title: str = "", style: str = "title") -> None:
    console.rule(f"[{style}]{title}[/{style}]" if title else "", style="muted")


def ask_text(prompt: str, default: Optional[str] = None) -> str:
    return Prompt.ask(f"[accent]{prompt}[/accent]", default=default, console=console)


def ask_int(prompt: str, default: Optional[int] = None,
            choices: Optional[Sequence[int]] = None) -> int:
    kwargs = {"console": console}
    if default is not None:
        kwargs["default"] = default
    if choices is not None:
        kwargs["choices"] = [str(c) for c in choices]
    return IntPrompt.ask(f"[accent]{prompt}[/accent]", **kwargs)


def confirm(prompt: str, default: bool = False) -> bool:
    return Confirm.ask(f"[accent]{prompt}[/accent]", default=default, console=console)


def choose(title: str, options: List[Tuple[str, str]], *,
           allow_back: bool = False, back_label: str = "Back") -> Optional[str]:
    """Render a numbered menu; return the chosen option key (or None if 'back').

    ``options`` is a list of (key, label) pairs. Labels may contain rich markup.
    """
    if title:
        console.print(Text(title, style="title"))
    display = list(options)
    if allow_back:
        display = display + [("__back__", f"[dim]{back_label}[/dim]")]
    for i, (_, label) in enumerate(display, start=1):
        console.print(f"  [accent]{i:>2}[/accent]) {label}")
    while True:
        choice = ask_int("Choose", default=1)
        if 1 <= choice <= len(display):
            key = display[choice - 1][0]
            return None if key == "__back__" else key
        console.print("[bad]Invalid choice.[/bad]")
