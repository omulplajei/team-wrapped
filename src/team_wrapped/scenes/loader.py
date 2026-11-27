"""Load scene and script definitions from the shared and data roots."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class LoadError(Exception):
    pass


ON_MISSING_DATA = ("skip", "fail")
_ENTRY_KEYS = {"scene", "on_missing_data", "duration", "scope", "transition"}


@dataclass(frozen=True)
class Entry:
    scene: str
    on_missing_data: str = "fail"
    duration: float | None = None
    scope: str | None = None
    transition: str | None = None


@dataclass(frozen=True)
class Script:
    id: str
    title: str
    period: object
    scope: str
    scenes: list
    music: dict | None = None
    transition: str = "fade"
    theme: str | None = None


@dataclass(frozen=True)
class Scene:
    id: str
    type: str
    title: str
    requires: list
    params: dict
    duration: float | None = None


def _read(kind: str, item_id: str, roots) -> tuple[dict, Path]:
    found = None
    for root in roots:
        candidate = Path(root) / kind / f"{item_id}.yml"
        if candidate.is_file():
            found = candidate  # later roots override earlier ones
    if found is None:
        searched = ", ".join(str(r) for r in roots)
        raise LoadError(f"{kind[:-1]} '{item_id}' not found in: {searched}")
    data = yaml.safe_load(found.read_text()) or {}
    if data.get("id") != item_id:
        raise LoadError(f"{found}: id '{data.get('id')}' does not match file name '{item_id}'")
    return data, found


def load_script(script_id: str, roots) -> Script:
    data, path = _read("scripts", script_id, roots)
    raw = data.get("scenes")
    if not isinstance(raw, list) or not raw:
        raise LoadError(f"{path}: 'scenes' must be a non-empty list")
    entries = []
    for item in raw:
        if not isinstance(item, dict) or "scene" not in item:
            raise LoadError(f"{path}: every entry needs a 'scene' key")
        unknown = set(item) - _ENTRY_KEYS
        if unknown:
            raise LoadError(f"{path}: unknown entry keys {sorted(unknown)}")
        mode = item.get("on_missing_data", "fail")
        if mode not in ON_MISSING_DATA:
            raise LoadError(f"{path}: on_missing_data must be one of {ON_MISSING_DATA}, got '{mode}'")
        entries.append(Entry(
            scene=item["scene"],
            on_missing_data=mode,
            duration=item.get("duration"),
            scope=item.get("scope"),
            transition=item.get("transition"),
        ))
    theme = data.get("theme")
    if theme is not None and not isinstance(theme, str):
        raise LoadError(f"{path}: 'theme' must be a theme name")
    return Script(
        id=script_id,
        title=data.get("title", script_id),
        period=data.get("period"),
        scope=data.get("scope", "all"),
        scenes=entries,
        music=data.get("music"),
        transition=data.get("transition", "fade"),
        theme=theme,
    )


def load_scene(scene_id: str, roots) -> Scene:
    data, path = _read("scenes", scene_id, roots)
    if not data.get("type"):
        raise LoadError(f"{path}: scene needs a 'type'")
    return Scene(
        id=scene_id,
        type=data["type"],
        title=data.get("title", scene_id),
        requires=data.get("requires") or [],
        params=data.get("params") or {},
        duration=data.get("duration"),
    )
