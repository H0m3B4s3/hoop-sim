"""Save-slot management on disk (under ``./saves/<uid>/``)."""
from __future__ import annotations

import os
import re
from typing import List, Optional

from hoopsim.config import AUTOSAVE_SLOT, SAVE_DIR_NAME
from hoopsim.models.world import World
from hoopsim.save.serialize import load_world, save_world

_SUFFIX = ".hoopsim.json"
_SLUG = re.compile(r"[^a-zA-Z0-9_-]+")


def saves_dir(uid: Optional[str] = None) -> str:
    base = os.path.join(os.getcwd(), SAVE_DIR_NAME)
    path = os.path.join(base, uid) if uid else base
    os.makedirs(path, exist_ok=True)
    return path


def _slug(slot: str) -> str:
    return _SLUG.sub("_", slot.strip()) or "save"


def slot_path(slot: str, uid: Optional[str] = None) -> str:
    return os.path.join(saves_dir(uid), _slug(slot) + _SUFFIX)


def list_saves(uid: Optional[str] = None) -> List[str]:
    out = []
    for fname in sorted(os.listdir(saves_dir(uid))):
        if fname.endswith(_SUFFIX):
            out.append(fname[: -len(_SUFFIX)])
    return out


def exists(slot: str, uid: Optional[str] = None) -> bool:
    return os.path.exists(slot_path(slot, uid))


def save_game(world: World, slot: str, uid: Optional[str] = None) -> str:
    path = slot_path(slot, uid)
    save_world(world, path)
    return path


def load_game(slot: str, uid: Optional[str] = None) -> World:
    return load_world(slot_path(slot, uid))


def autosave(world: World, uid: Optional[str] = None) -> None:
    save_game(world, AUTOSAVE_SLOT, uid)


def delete_save(slot: str, uid: Optional[str] = None) -> None:
    path = slot_path(slot, uid)
    if os.path.exists(path):
        os.remove(path)
