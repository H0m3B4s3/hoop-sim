"""World (de)serialization with a schema-version envelope and migration hook."""
from __future__ import annotations

import json

from hoopr.config import SCHEMA_VERSION
from hoopr.models.world import World


def migrate(data: dict) -> dict:
    """Upgrade an older save dict to the current schema. Identity for v1."""
    version = data.get("schema_version", 1)
    # Future migrations: while version < SCHEMA_VERSION: ... ; version += 1
    data["schema_version"] = SCHEMA_VERSION if version > SCHEMA_VERSION else version
    return data


def world_to_json(world: World) -> str:
    return json.dumps(world.to_dict(), separators=(",", ":"))


def world_from_json(text: str) -> World:
    data = migrate(json.loads(text))
    return World.from_dict(data)


def save_world(world: World, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(world_to_json(world))


def load_world(path: str) -> World:
    with open(path, "r", encoding="utf-8") as fh:
        return world_from_json(fh.read())
