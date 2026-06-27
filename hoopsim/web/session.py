"""In-memory holder for the live game state behind the web API.

Each browser session is identified by a persistent cookie (the sid). Saves are
namespaced to that sid so users only see their own files.
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

    # -- persistence (saves namespaced by sid) --------------------------------
    def save(self, sid: str, slot: str) -> str:
        return store.save_game(self.require(sid), slot, uid=sid)

    def autosave(self, sid: str) -> None:
        store.autosave(self.require(sid), uid=sid)

    def load(self, sid: str, slot: str) -> World:
        world = store.load_game(slot, uid=sid)
        self.set(sid, world)
        return world

    def list_saves(self, sid: str):
        return store.list_saves(uid=sid)


SESSIONS = SessionStore()
