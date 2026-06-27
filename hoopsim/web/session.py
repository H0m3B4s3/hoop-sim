"""In-memory holder for the live game state behind the web API.

HoopSim is a single-player local app, so we keep one active ``World`` per browser session
(keyed by a cookie). Persistence still goes through ``hoopr.save.store`` exactly as the
terminal app does — sessions are just the live, unsaved game in memory.
"""
from __future__ import annotations

import threading
import uuid
from typing import Dict, Optional

from hoopsim.models.world import World
from hoopsim.save import store


class SessionStore:
    def __init__(self) -> None:
        self._worlds: Dict[str, World] = {}
        self._lock = threading.Lock()

    def new_session(self) -> str:
        return uuid.uuid4().hex

    def get(self, sid: str) -> Optional[World]:
        return self._worlds.get(sid)

    def require(self, sid: str) -> World:
        world = self._worlds.get(sid)
        if world is None:
            raise KeyError("No active game for this session. Start or load a career first.")
        return world

    def set(self, sid: str, world: World) -> None:
        with self._lock:
            self._worlds[sid] = world

    def clear(self, sid: str) -> None:
        with self._lock:
            self._worlds.pop(sid, None)

    # -- persistence (thin wrappers over hoopr.save.store) ------------------
    def save(self, sid: str, slot: str) -> str:
        return store.save_game(self.require(sid), slot)

    def autosave(self, sid: str) -> None:
        store.autosave(self.require(sid))

    def load(self, sid: str, slot: str) -> World:
        world = store.load_game(slot)
        self.set(sid, world)
        return world

    @staticmethod
    def list_saves():
        return store.list_saves()


SESSIONS = SessionStore()
