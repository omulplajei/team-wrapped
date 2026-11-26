"""Validate a script's scenes against the derived data and the dataset catalog."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .catalog import load_catalog
from .derived import DerivedData, has_field, resolve_ref
from .loader import Scene, Script, load_scene, load_script
from .scene_types import SceneType, load_scene_types


@dataclass
class SceneResult:
    scene_id: str
    status: str  # supported | partial | unsupported
    problems: list
    skipped: bool = False


@dataclass
class Report:
    script_id: str
    results: list

    @property
    def ok(self) -> bool:
        return all(r.status != "unsupported" or r.skipped for r in self.results)


@dataclass
class Resolved:
    script: Script
    scenes: dict
    derived: DerivedData
    scene_types: dict
    report: Report


def validate_script(script: Script, scenes: dict, derived: DerivedData,
                    catalog: set, scene_types: dict) -> Report:
    partial_names = derived.partial_datasets()
    results = []
    for entry in script.scenes:
        scene: Scene = scenes[entry.scene]
        scope_key = derived.scope_key(entry.scope or script.scope)
        problems: list[str] = []
        partial = False

        stype: SceneType | None = scene_types.get(scene.type)
        if stype is None:
            problems.append(f"unknown scene type '{scene.type}'")
        else:
            for key in stype.required_params:
                if key not in scene.params:
                    problems.append(f"missing required param '{key}'")

        datasets = {}
        for req in scene.requires:
            name = req["dataset"]
            if name not in catalog:
                problems.append(f"dataset '{name}' is not in the catalog")
                continue
            node = derived.dataset(name, scope_key)
            if node is None:
                problems.append(f"no data for '{name}' in scope '{scope_key}'")
                continue
            datasets[name] = node
            for field in req.get("fields", []):
                if not has_field(node, field):
                    problems.append(f"'{name}' is missing field '{field}'")
            if name in partial_names:
                if req.get("allow_partial", False):
                    partial = True
                else:
                    problems.append(f"'{name}' is partial but this scene does not allow partial data")

        for item in scene.params.get("items", []):
            ref = item.get("value") if isinstance(item, dict) else None
            if ref is not None and resolve_ref(datasets, ref) is None:
                problems.append(f"value '{ref}' does not resolve to required data")

        status = "unsupported" if problems else ("partial" if partial else "supported")
        results.append(SceneResult(
            scene_id=scene.id,
            status=status,
            problems=problems,
            skipped=status == "unsupported" and entry.on_missing_data == "skip",
        ))
    return Report(script_id=script.id, results=results)


def resolve_and_validate(script_id: str, repo_root, data_root) -> Resolved:
    repo_root, data_root = Path(repo_root), Path(data_root)
    roots = [repo_root, data_root]
    script = load_script(script_id, roots)
    scenes = {entry.scene: load_scene(entry.scene, roots) for entry in script.scenes}
    derived = DerivedData(data_root)
    catalog = load_catalog(repo_root / "docs" / "datasets.md")
    scene_types = load_scene_types(repo_root / "web")
    report = validate_script(script, scenes, derived, catalog, scene_types)
    return Resolved(script, scenes, derived, scene_types, report)


def format_report(report: Report) -> str:
    lines = [report.script_id]
    for r in report.results:
        suffix = " (skipped)" if r.skipped else ""
        lines.append(f"  {r.scene_id}: {r.status}{suffix}")
        lines.extend(f"    - {p}" for p in r.problems)
    return "\n".join(lines)
