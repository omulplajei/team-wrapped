"""Build a self-contained HTML page that plays a script (spec section 13)."""
from __future__ import annotations

import html
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .validate import Report, Resolved, resolve_and_validate

# (folder under web/, file name) copied next to the page in assets/
_PLAYER_ASSETS = [
    ("player", "player.css"),
    ("player", "timing.js"),
    ("player", "player.js"),
    ("presets", "presets.js"),
]


class BuildError(Exception):
    def __init__(self, message: str, report: Report | None = None):
        super().__init__(message)
        self.report = report


@dataclass
class BuildResult:
    out_dir: Path
    index: Path
    skipped: list = field(default_factory=list)


def transform_renderer(name: str, source: str) -> str:
    """Rewrite `export default X` into a registry assignment so the file runs as a classic script."""
    if re.search(r"^\s*import\s", source, re.M):
        raise BuildError(f"scene type '{name}': render.js must not use import (pages open from disk)")
    if source.count("export default") != 1:
        raise BuildError(f"scene type '{name}': render.js needs exactly one 'export default'")
    return f'TeamWrapped.sceneTypes["{name}"] = ' + source.replace("export default", "", 1)


def _payload(resolved: Resolved) -> tuple[dict, list]:
    script, derived = resolved.script, resolved.derived
    partial_all = derived.partial_datasets()
    scenes, skipped = [], []
    for entry, result in zip(script.scenes, resolved.report.results):
        if result.skipped:
            skipped.append(entry.scene)
            continue
        scene = resolved.scenes[entry.scene]
        scope = entry.scope or script.scope
        key = derived.scope_key(scope)
        data = {req["dataset"]: derived.dataset(req["dataset"], key) for req in scene.requires}
        stype = resolved.scene_types[scene.type]
        scenes.append({
            "id": scene.id,
            "title": scene.title,
            "type": scene.type,
            "duration": float(entry.duration or scene.duration or stype.default_duration),
            "params": scene.params,
            "data": data,
            "partial": sorted(name for name in data if name in partial_all),
            "scope": scope,
            "transition": entry.transition or script.transition,
        })
    payload = {
        "script": {
            "id": script.id,
            "title": script.title,
            "period": script.period,
            "scope": script.scope,
            "transition": script.transition,
            "music": None,
        },
        "scenes": scenes,
    }
    return payload, skipped


def _prepare_music(music: dict | None, data_root: Path, out_dir: Path) -> dict | None:
    if not music:
        return None
    file = music.get("file")
    if not file:
        raise BuildError("music.file is required when music is set")
    spec = {"volume": music.get("volume", 0.5), "loop": music.get("loop", True)}
    if str(file).startswith(("http://", "https://")):
        spec["src"] = file
        return spec
    source = data_root / "assets" / file
    if not source.is_file():
        raise BuildError(f"music file '{file}' not found in {data_root / 'assets'}")
    dest = out_dir / "assets" / "music"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest / source.name)
    spec["src"] = f"assets/music/{source.name}"
    return spec


def build(script_id: str, repo_root, data_root, out_root) -> BuildResult:
    repo_root, data_root, out_root = Path(repo_root), Path(data_root), Path(out_root)
    resolved = resolve_and_validate(script_id, repo_root, data_root)
    if not resolved.report.ok:
        raise BuildError("script has unsupported scenes", resolved.report)

    web = repo_root / "web"
    vendor = web / "vendor"
    if not (vendor / "gsap.min.js").is_file():
        raise BuildError(f"{vendor / 'gsap.min.js'} is missing; vendor GSAP first")

    payload, skipped = _payload(resolved)
    if not payload["scenes"]:
        raise BuildError("no scenes left to play after skipping unsupported ones")

    out_dir = out_root / resolved.script.id
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)
    payload["script"]["music"] = _prepare_music(resolved.script.music, data_root, out_dir)

    for folder, name in _PLAYER_ASSETS:
        shutil.copy2(web / folder / name, out_dir / "assets" / name)
    shutil.copytree(vendor, out_dir / "assets" / "vendor", dirs_exist_ok=True)
    if (data_root / "avatars").is_dir():
        shutil.copytree(data_root / "avatars", out_dir / "avatars", dirs_exist_ok=True)

    used_types = sorted({scene["type"] for scene in payload["scenes"]})
    renderers = "\n".join(
        transform_renderer(name, (resolved.scene_types[name].dir / "render.js").read_text())
        for name in used_types
    )
    data_tag = ('<script type="application/json" id="tw-data">'
                + json.dumps(payload).replace("</", "<\\/") + "</script>")
    renderer_tag = ("<script>\nwindow.TeamWrapped = window.TeamWrapped || {};\n"
                    "TeamWrapped.sceneTypes = {};\n" + renderers + "\n</script>")

    page = (web / "player" / "index.template.html").read_text()
    page = (page.replace("{{TITLE}}", html.escape(resolved.script.title))
                .replace("<!--TW_DATA-->", data_tag)
                .replace("<!--TW_RENDERERS-->", renderer_tag))
    index = out_dir / "index.html"
    index.write_text(page)
    return BuildResult(out_dir=out_dir, index=index, skipped=skipped)
