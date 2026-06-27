"""Save-slot management on disk (under ``./saves``)."""
from __future__ import annotations

import os
import re
from typing import List

from hoopsim.config import AUTOSAVE_SLOT, SAVE_DIR_NAME
from hoopsim.models.world import World
from hoopsim.save.serialize import load_world, save_world

_SUFFIX = ".hoopsim.json"
_SLUG = re.compile(r"[^a-zA-Z0-9_-]+")


def saves_dir() -> str:
    path = os.path.join(os.getcwd(), SAVE_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def _slug(slot: str) -> str:
    return _SLUG.sub("_", slot.strip()) or "save"


def slot_path(slot: str) -> str:
    return os.path.join(saves_dir(), _slug(slot) + _SUFFIX)


def list_saves() -> List[str]:
    out = []
    for fname in sorted(os.listdir(saves_dir())):
        if fname.endswith(_SUFFIX):
            out.append(fname[: -len(_SUFFIX)])
    return out


def exists(slot: str) -> bool:
    return os.path.exists(slot_path(slot))


def save_game(world: World, slot: str) -> str:
    path = slot_path(slot)
    save_world(world, path)
    return path


def load_game(slot: str) -> World:
    return load_world(slot_path(slot))


def autosave(world: World) -> None:
    save_game(world, AUTOSAVE_SLOT)


def delete_save(slot: str) -> None:
    path = slot_path(slot)
    if os.path.exists(path):
        os.remove(path)
