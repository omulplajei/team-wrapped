"""Validate a script's scenes against the derived data and the dataset catalog."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .catalog import load_catalog
from .derived import DerivedData, has_field, resolve_ref
from .loader import Scene, Script, load_scene, load_script
from .scene_types import SceneType, load_scene_types


def _value_refs(params: dict, include_top_level_value: bool) -> list[str]:
    """Data references in a scene's params: items[].value and supporting[].value, plus the
    top-level value when the scene type declares it as a required (reference) param."""
    refs = []
    if include_top_level_value and isinstance(params.get("value"), str):
        refs.append(params["value"])
    for key in ("items", "supporting", "steps"):
        entries = params.get(key)
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and isinstance(entry.get("value"), str):
                    refs.append(entry["value"])
    return refs


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

        top_level = stype is not None and "value" in stype.required_params
        for ref in _value_refs(scene.params, top_level):
            value = resolve_ref(datasets, ref)
            if value is None:
                problems.append(f"value '{ref}' does not resolve to required data")
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                problems.append(f"value '{ref}' is not a number")
        for list_param in ("names", "records"):
            list_ref = scene.params.get(list_param)
            if isinstance(list_ref, str) and not isinstance(resolve_ref(datasets, list_ref), list):
                problems.append(f"{list_param} '{list_ref}' does not resolve to a list")

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
