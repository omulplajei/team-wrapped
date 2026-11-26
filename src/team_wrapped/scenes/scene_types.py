"""Scene type definitions: one folder per type under web/scene-types/."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .loader import LoadError


@dataclass(frozen=True)
class SceneType:
    name: str
    default_duration: float
    required_params: list
    dir: Path


def load_scene_types(web_dir) -> dict[str, SceneType]:
    types: dict[str, SceneType] = {}
    for yml in sorted((Path(web_dir) / "scene-types").glob("*/type.yml")):
        data = yaml.safe_load(yml.read_text()) or {}
        name = data.get("name")
        if name != yml.parent.name:
            raise LoadError(f"{yml}: name '{name}' does not match folder '{yml.parent.name}'")
        if "default_duration" not in data:
            raise LoadError(f"{yml}: default_duration is required")
        types[name] = SceneType(
            name=name,
            default_duration=float(data["default_duration"]),
            required_params=list(data.get("required_params", [])),
            dir=yml.parent,
        )
    return types
