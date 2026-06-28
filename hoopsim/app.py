"""Top-level application entry.

Phase-1 scaffold: this boots the rich UI and hands control to the main menu screen. The full
navigation stack and screens are built out in the ``hoopsim.ui`` package; until those land this
module provides a runnable smoke entry point.
"""
from __future__ import annotations

from hoopsim import __version__


def run() -> None:
    try:
        from hoopsim.ui.app_ui import main_loop
    except Exception:  # pragma: no cover - UI not built yet during early scaffolding
        _fallback_banner()
        return
    main_loop()


def _fallback_banner() -> None:
    print(f"HoopSim v{__version__} — basketball management sim")
    print("UI not yet available. Run the test suite with `pytest` to exercise the engine.")


if __name__ == "__main__":
    run()
