"""Build a self-contained HTML page that plays a script (spec section 13)."""
from __future__ import annotations

import html
import json
import re
import shutil
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from ..aggregate.contributors import PLACEHOLDER_AVATAR
from .theme import css_overrides, load_theme
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
    warnings: list = field(default_factory=list)


def transform_renderer(name: str, source: str) -> str:
    """Rewrite `export default X` into a registry assignment so the file runs as a classic script."""
    if re.search(r"^\s*import\s", source, re.M):
        raise BuildError(f"scene type '{name}': render.js must not use import (pages open from disk)")
    if source.count("export default") != 1:
        raise BuildError(f"scene type '{name}': render.js needs exactly one 'export default'")
    body = source.replace("export default", f'TeamWrapped.sceneTypes["{name}"] =', 1)
    return f"(function () {{\n{body}\n}})();"


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


def _prepare_music(music: dict | None, data_root: Path) -> tuple[dict | None, tuple[Path, str] | None]:
    """Validate music; return (spec, (source file, real name)) with nothing written."""
    if not music:
        return None, None
    file = music.get("file")
    if not file:
        raise BuildError("music.file is required when music is set")
    volume = music.get("volume", 0.5)
    if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not 0 <= volume <= 1:
        raise BuildError(f"music volume must be a number between 0 and 1, got {volume!r}")
    spec = {"volume": volume, "loop": music.get("loop", True)}
    if str(file).startswith(("http://", "https://")):
        spec["src"] = file
        return spec, None
    assets = data_root / "assets"
    if Path(str(file)).is_absolute():
        raise BuildError(f"music file '{file}' must be relative to {assets}")
    source = (assets / file).resolve()
    if not source.is_relative_to(assets.resolve()):
        raise BuildError(f"music file '{file}' must stay inside {assets}")
    if not source.is_file():
        raise BuildError(f"music file '{file}' not found in {assets}")
    spec["src"] = "assets/music/" + urllib.parse.quote(source.name)
    return spec, (source, source.name)


def _avatar_files(node) -> set[str]:
    """Every string value of an 'avatar_file' key anywhere inside the payload."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "avatar_file" and isinstance(value, str):
                found.add(value)
            else:
                found |= _avatar_files(value)
    elif isinstance(node, list):
        for item in node:
            found |= _avatar_files(item)
    return found


def _replace_avatars(node, replace: dict) -> None:
    """Point every 'avatar_file' value found in `replace` at its replacement, in place."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "avatar_file" and isinstance(value, str):
                node[key] = replace.get(value, value)
            else:
                _replace_avatars(value, replace)
    elif isinstance(node, list):
        for item in node:
            _replace_avatars(item, replace)


def _prepare_avatars(payload: dict, data_root: Path) -> tuple[list[tuple[Path, str]], list[str]]:
    """Validate avatar references; return (source, relative name) for the files to copy, and warnings.
    A reference to a missing file is pointed at the placeholder when data/avatars/placeholder.png exists, so the
    page never shows a broken image; without a placeholder it is left as is and a warning says so."""
    root = data_root.resolve()
    copies, warnings, replace = [], [], {}
    placeholder = data_root / PLACEHOLDER_AVATAR
    for ref in sorted(_avatar_files(payload)):
        if Path(ref).is_absolute():
            raise BuildError(f"avatar file '{ref}' must be relative to {data_root}")
        source = (data_root / ref).resolve()
        if not source.is_relative_to(root):
            raise BuildError(f"avatar file '{ref}' must stay inside {data_root}")
        if source.is_file():
            copies.append((source, ref))
        elif ref != PLACEHOLDER_AVATAR and placeholder.is_file():
            replace[ref] = PLACEHOLDER_AVATAR
        else:
            warnings.append(f"avatar file '{ref}' not found in {data_root} and no {PLACEHOLDER_AVATAR} to fall back "
                            "to; the page will show a broken image")
    if replace:
        _replace_avatars(payload, replace)
        if all(ref != PLACEHOLDER_AVATAR for _, ref in copies):
            copies.append((placeholder.resolve(), PLACEHOLDER_AVATAR))
    return copies, warnings


def _embed_json(payload: dict) -> str:
    text = json.dumps(payload, allow_nan=False)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def build(script_id: str, repo_root, data_root, out_root, theme: str | None = None) -> BuildResult:
    repo_root, data_root, out_root = Path(repo_root), Path(data_root), Path(out_root)
    resolved = resolve_and_validate(script_id, repo_root, data_root)
    if not resolved.report.ok:
        raise BuildError("script has unsupported scenes", resolved.report)

    web = repo_root / "web"
    vendor = web / "vendor"
    if not (vendor / "gsap.min.js").is_file():
        raise BuildError(f"{vendor / 'gsap.min.js'} is missing; vendor GSAP first")

    chosen = load_theme(theme or resolved.script.theme or "default",
                        [repo_root, repo_root / "data", data_root])
    theme_files = list(dict.fromkeys(
        ([chosen.logo] if chosen.logo else []) + list(chosen.logos.values()) + list(chosen.backdrop_images)))
    page_path = {path: "assets/theme/" + urllib.parse.quote(path.name) for path in theme_files}

    payload, skipped = _payload(resolved)
    if not payload["scenes"]:
        raise BuildError("no scenes left to play after skipping unsupported ones")

    # The player gets only what scenes and the backdrop use: null when the theme has neither.
    theme_payload = {}
    if chosen.backdrop_images:
        theme_payload["backdrop"] = {
            "images": [page_path[path] for path in chosen.backdrop_images],
            "opacity": chosen.backdrop_opacity}
    if chosen.logos:
        theme_payload["logos"] = {name: page_path[path] for name, path in chosen.logos.items()}
    payload["script"]["theme"] = theme_payload or None

    payload["script"]["music"], music_file = _prepare_music(resolved.script.music, data_root)

    avatars, warnings = _prepare_avatars(payload, data_root)

    used_types = sorted({scene["type"] for scene in payload["scenes"]})
    renderers = "\n".join(
        transform_renderer(name, (resolved.scene_types[name].dir / "render.js").read_text())
        for name in used_types
    )
    data_tag = '<script type="application/json" id="tw-data">' + _embed_json(payload) + "</script>"
    renderer_tag = ("<script>\nwindow.TeamWrapped = window.TeamWrapped || {};\n"
                    "TeamWrapped.sceneTypes = {};\n" + renderers + "\n</script>")
    overrides = css_overrides(chosen)
    logo_tag = ('<img class="tw-logo" src="' + page_path[chosen.logo] + '" alt="">') if chosen.logo else ""
    replacements = {
        "<!--TW_THEME-->": ('<style id="tw-theme">' + overrides + "</style>") if overrides else "",
        "<!--TW_LOGO-->": logo_tag,
        "{{TITLE}}": html.escape(resolved.script.title),
        "<!--TW_DATA-->": data_tag,
        "<!--TW_RENDERERS-->": renderer_tag,
    }
    template = (web / "player" / "index.template.html").read_text()
    page = re.sub("|".join(re.escape(key) for key in replacements),
                  lambda m: replacements[m.group(0)], template)

    script_id = resolved.script.id
    if Path(script_id).name != script_id or script_id in ("", ".", ".."):
        raise BuildError(f"script id '{script_id}' is not a plain name")

    # everything is validated: only now touch the output folder
    out_dir = out_root / script_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "assets").mkdir(parents=True)
    if music_file:
        (out_dir / "assets" / "music").mkdir()
        shutil.copy2(music_file[0], out_dir / "assets" / "music" / music_file[1])
    for folder, name in _PLAYER_ASSETS:
        shutil.copy2(web / folder / name, out_dir / "assets" / name)
    shutil.copytree(vendor, out_dir / "assets" / "vendor")
    for source, ref in avatars:
        target = out_dir / ref
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    if theme_files:
        (out_dir / "assets" / "theme").mkdir()
        for path in theme_files:
            shutil.copy2(path, out_dir / "assets" / "theme" / path.name)
    index = out_dir / "index.html"
    index.write_text(page)
    return BuildResult(out_dir=out_dir, index=index, skipped=skipped, warnings=warnings)
