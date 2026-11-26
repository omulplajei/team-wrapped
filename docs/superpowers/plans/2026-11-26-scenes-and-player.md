# Scenes, Validation, Build and Player Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load scenes and scripts, validate a script against the planned datasets, and build a self-contained HTML page that plays the Year Wrapped (Play/Pause, progress line with jumping, background music with mute, animated scenes), all running on `data-sample/`.

**Architecture:** A Python package (`team_wrapped.scenes`) loads scene and script YAML, checks every scene's `requires` against the derived-data files and the dataset catalog, and the `build` command embeds the resolved data and the scene renderers into one HTML page. The page is driven by a small classic-script player on top of GSAP timelines. No GitHub access is needed.

**Tech Stack:** Python 3.11+ (PyYAML, pytest), JavaScript (classic scripts, GSAP vendored, `node --test` for pure logic).

**Series.** This is plan 1 of 3. Plan 2 is the aggregator (raw records to derived files). Plan 3 is the collector (GitHub to raw records). The spec is `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`.

## Global Constraints

- Python 3.11+; dependencies: PyYAML, pytest (spec section 2).
- GSAP is vendored in `web/vendor/` together with its licence text and copied into each built page, so pages work offline (spec section 13).
- `data/` and `dist/` are git-ignored; nothing project-specific (org, repo or group names, emails) is ever committed (spec sections 1, 3).
- Derived file format is `{"period": ..., "scopes": {"all": {...}, "group:<name>": {...}}}`; dataset `family.name` resolves to `<family>.json` then `scopes[<scope>][name]`; `contributors` resolves to `scopes[<scope>]` (spec section 7.6).
- Shared scenes are scope-agnostic: they never name a repo or group (spec section 12).
- A scene may only require datasets listed in `docs/datasets.md` (spec section 12).
- Loader order is shared root first, then the data root; a file with the same `id` in the data root overrides the shared one (spec section 12).
- On a `build`, unsupported scenes with `on_missing_data: fail` stop the build; those with `skip` are left out and listed (spec section 13).
- Music files are never committed; they are referenced from `data/assets/` or by URL (spec section 13).
- Humans in the headcount scene are `human` plus `unlinked` contributors; robots are `bot` (decided in brainstorming).
- Pages must open from disk with no server, so renderers and player use classic scripts, never ES-module imports (browsers block those on `file://`).
- Run the CLI without installing: `PYTHONPATH=src python3 -m team_wrapped ...`. Tests need no install (`pythonpath = ["src"]` in `pyproject.toml`).

## File Structure

```
pyproject.toml
src/team_wrapped/__init__.py
src/team_wrapped/__main__.py
src/team_wrapped/cli.py                    # validate-script, build
src/team_wrapped/scenes/__init__.py
src/team_wrapped/scenes/loader.py          # Scene, Script, Entry, load_scene, load_script
src/team_wrapped/scenes/derived.py         # DerivedData, has_field, resolve_ref
src/team_wrapped/scenes/catalog.py         # load_catalog(docs/datasets.md) -> set of names
src/team_wrapped/scenes/scene_types.py     # SceneType, load_scene_types(web/)
src/team_wrapped/scenes/validate.py        # validate_script, resolve_and_validate, format_report
src/team_wrapped/scenes/build.py           # build(), BuildError, transform_renderer
tests/conftest.py
tests/scenes/test_loader.py
tests/scenes/test_derived.py
tests/scenes/test_catalog_and_types.py
tests/scenes/test_validate.py
tests/scenes/test_cli_validate.py
tests/scenes/test_build.py
tests-js/timing.test.js
tests-js/presets.test.js
web/player/index.template.html
web/player/player.css
web/player/timing.js                       # pure timing helpers (node-testable)
web/player/player.js                       # playback controller
web/presets/presets.js                     # format, lookup, animation presets
web/scene-types/message/{type.yml,render.js}
web/scene-types/stats/{type.yml,render.js}
web/scene-types/headcount/{type.yml,render.js}
web/vendor/gsap.min.js, web/vendor/GSAP-LICENSE.md
README.md
```

---

### Task 1: Project scaffold and script/scene loader

**Files:**
- Create: `pyproject.toml`, `src/team_wrapped/__init__.py`, `src/team_wrapped/scenes/__init__.py`, `src/team_wrapped/scenes/loader.py`
- Create: `tests/conftest.py`, `tests/scenes/test_loader.py`

**Interfaces:**
- Produces:
  - `LoadError(Exception)`
  - `Entry(scene: str, on_missing_data: str = "fail", duration: float | None = None, scope: str | None = None, transition: str | None = None)`
  - `Script(id, title, period, scope, scenes: list[Entry], music: dict | None = None, transition: str = "fade")`
  - `Scene(id, type, title, requires: list[dict], params: dict, duration: float | None = None)`
  - `load_script(script_id: str, roots: list[Path]) -> Script`
  - `load_scene(scene_id: str, roots: list[Path]) -> Scene`
  - Each root is a directory containing `scripts/` and `scenes/`. Later roots override earlier ones.
  - Pytest fixtures `repo_root` and `sample_root` (a `Path` to the repo root and to `data-sample/`).

- [ ] **Step 1: Create a working branch**

```bash
git checkout -b feature/scenes-and-player
```
Expected: `Switched to a new branch 'feature/scenes-and-player'`

- [ ] **Step 2: Create the scaffold files**

`pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "team-wrapped"
version = "0.1.0"
description = "Collect GitHub activity and play it back as a wrapped-style page"
requires-python = ">=3.11"
dependencies = ["PyYAML>=6"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
team-wrapped = "team_wrapped.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

`src/team_wrapped/__init__.py`:
```python
__version__ = "0.1.0"
```

`src/team_wrapped/scenes/__init__.py`: empty file.

`tests/conftest.py`:
```python
import pathlib

import pytest


@pytest.fixture
def repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_root(repo_root) -> pathlib.Path:
    return repo_root / "data-sample"
```

- [ ] **Step 3: Write the failing tests**

`tests/scenes/test_loader.py`:
```python
import pytest

from team_wrapped.scenes.loader import Entry, LoadError, load_scene, load_script


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def make_root(tmp_path, name):
    root = tmp_path / name
    root.mkdir()
    return root


def test_load_script_reads_entries_and_defaults(tmp_path):
    shared = make_root(tmp_path, "shared")
    write(shared / "scripts/s.yml", """
id: s
title: S title
period: 2026
scope: all
scenes:
  - scene: a
  - scene: b
    on_missing_data: skip
    duration: 5
""")
    script = load_script("s", [shared])
    assert script.title == "S title"
    assert script.period == 2026
    assert script.scope == "all"
    assert script.transition == "fade"
    assert script.music is None
    assert script.scenes == [Entry(scene="a"), Entry(scene="b", on_missing_data="skip", duration=5)]


def test_load_scene_defaults(tmp_path):
    shared = make_root(tmp_path, "shared")
    write(shared / "scenes/m.yml", "id: m\ntype: message\nparams: {text: hi}\n")
    scene = load_scene("m", [shared])
    assert scene.type == "message"
    assert scene.title == "m"          # title defaults to the id
    assert scene.requires == []
    assert scene.params == {"text": "hi"}
    assert scene.duration is None


def test_later_root_overrides_earlier(tmp_path):
    shared = make_root(tmp_path, "shared")
    private = make_root(tmp_path, "private")
    write(shared / "scenes/m.yml", "id: m\ntype: message\nparams: {text: shared}\n")
    write(private / "scenes/m.yml", "id: m\ntype: message\nparams: {text: private}\n")
    assert load_scene("m", [shared, private]).params["text"] == "private"
    assert load_scene("m", [shared]).params["text"] == "shared"


def test_missing_file_raises(tmp_path):
    shared = make_root(tmp_path, "shared")
    with pytest.raises(LoadError, match="scene 'nope' not found"):
        load_scene("nope", [shared])


def test_id_must_match_file_name(tmp_path):
    shared = make_root(tmp_path, "shared")
    write(shared / "scenes/m.yml", "id: other\ntype: message\n")
    with pytest.raises(LoadError, match="does not match file name"):
        load_scene("m", [shared])


def test_script_rejects_bad_on_missing_data_and_unknown_keys(tmp_path):
    shared = make_root(tmp_path, "shared")
    write(shared / "scripts/bad1.yml", "id: bad1\nscenes:\n  - scene: a\n    on_missing_data: maybe\n")
    write(shared / "scripts/bad2.yml", "id: bad2\nscenes:\n  - scene: a\n    durtion: 3\n")
    write(shared / "scripts/bad3.yml", "id: bad3\nscenes: []\n")
    with pytest.raises(LoadError, match="on_missing_data"):
        load_script("bad1", [shared])
    with pytest.raises(LoadError, match="unknown entry keys"):
        load_script("bad2", [shared])
    with pytest.raises(LoadError, match="non-empty list"):
        load_script("bad3", [shared])


def test_scene_requires_a_type(tmp_path):
    shared = make_root(tmp_path, "shared")
    write(shared / "scenes/m.yml", "id: m\n")
    with pytest.raises(LoadError, match="needs a 'type'"):
        load_scene("m", [shared])
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python3 -m pytest tests/scenes/test_loader.py -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'team_wrapped.scenes.loader'`

- [ ] **Step 5: Write the implementation**

`src/team_wrapped/scenes/loader.py`:
```python
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
    return Script(
        id=script_id,
        title=data.get("title", script_id),
        period=data.get("period"),
        scope=data.get("scope", "all"),
        scenes=entries,
        music=data.get("music"),
        transition=data.get("transition", "fade"),
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/scenes/test_loader.py -v`
Expected: 7 passed

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src tests
git commit -m "Add project scaffold and scene/script loader" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Derived data access

**Files:**
- Create: `src/team_wrapped/scenes/derived.py`
- Test: `tests/scenes/test_derived.py`

**Interfaces:**
- Consumes: derived file layout from spec 7.6 (the files in `data-sample/derived/`).
- Produces:
  - `DerivedData(data_root)` with `.dataset(name: str, scope_key: str) -> object | None`, `.partial_datasets() -> set[str]`, `.meta() -> dict`, and static `DerivedData.scope_key(scope: str) -> str` (`"all"` stays `"all"`, `"alpha"` becomes `"group:alpha"`, values starting `group:` or `repo:` stay as they are).
  - `has_field(node, path: str) -> bool`: dotted path; where a value is a list, the rest of the path must be present on at least one item.
  - `resolve_ref(datasets: dict, ref: str) -> object | None`: `ref` such as `summary.totals.commits`; dataset names are tried as the first two segments, then the first one.

- [ ] **Step 1: Write the failing tests**

`tests/scenes/test_derived.py`:
```python
from team_wrapped.scenes.derived import DerivedData, has_field, resolve_ref


def test_scope_key():
    assert DerivedData.scope_key("all") == "all"
    assert DerivedData.scope_key("alpha") == "group:alpha"
    assert DerivedData.scope_key("group:alpha") == "group:alpha"
    assert DerivedData.scope_key("repo:api") == "repo:api"


def test_dataset_lookup_on_sample(sample_root):
    d = DerivedData(sample_root)
    assert d.dataset("summary.totals", "all")["commits"] == 1240
    assert d.dataset("contributors", "all")["total"] == 13
    assert d.dataset("contributors", "group:alpha")["total"] == 10
    assert d.dataset("summary.nope", "all") is None            # unknown dataset name
    assert d.dataset("review_collab.reviews", "all") is None   # family file does not exist
    assert d.dataset("summary.totals", "group:nope") is None   # unknown scope


def test_partial_datasets_from_meta(sample_root, tmp_path):
    assert DerivedData(sample_root).partial_datasets() == {"delivery_volume.lines"}
    assert DerivedData(tmp_path).partial_datasets() == set()   # no meta.json at all


def test_has_field():
    node = {"total": 3, "by_kind": {"bot": 1},
            "list": [{"kind": "human", "login": "a"}, {"kind": "unlinked"}]}
    assert has_field(node, "total")
    assert has_field(node, "by_kind.bot")
    assert has_field(node, "list.kind")
    assert has_field(node, "list.login")      # present on at least one item
    assert not has_field(node, "list.email")
    assert not has_field(node, "nope")


def test_resolve_ref():
    datasets = {"summary.totals": {"commits": 5}, "contributors": {"total": 2}}
    assert resolve_ref(datasets, "summary.totals.commits") == 5
    assert resolve_ref(datasets, "contributors.total") == 2
    assert resolve_ref(datasets, "summary.totals.nope") is None
    assert resolve_ref(datasets, "other.thing.value") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/scenes/test_derived.py -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'team_wrapped.scenes.derived'`

- [ ] **Step 3: Write the implementation**

`src/team_wrapped/scenes/derived.py`:
```python
"""Read the derived files written by `aggregate` (spec section 7.6)."""
from __future__ import annotations

import json
from pathlib import Path


class DerivedData:
    def __init__(self, data_root):
        self.data_root = Path(data_root)
        self._cache: dict[str, dict | None] = {}

    @staticmethod
    def scope_key(scope: str) -> str:
        if scope == "all" or scope.startswith(("group:", "repo:")):
            return scope
        return f"group:{scope}"

    def _file(self, family: str) -> dict | None:
        if family not in self._cache:
            path = self.data_root / "derived" / f"{family}.json"
            self._cache[family] = json.loads(path.read_text()) if path.is_file() else None
        return self._cache[family]

    def meta(self) -> dict:
        return self._file("meta") or {}

    def partial_datasets(self) -> set[str]:
        return set(self.meta().get("partial_datasets", []))

    def dataset(self, name: str, scope_key: str):
        family, _, rest = name.partition(".")
        data = self._file(family)
        if data is None:
            return None
        node = data.get("scopes", {}).get(scope_key)
        if node is None:
            return None
        return node.get(rest) if rest else node


def has_field(node, path: str) -> bool:
    """True if `path` exists. Through a list, it must exist on at least one item."""
    if isinstance(node, list):
        return any(has_field(item, path) for item in node)
    head, _, rest = path.partition(".")
    if not isinstance(node, dict) or head not in node:
        return False
    return not rest or has_field(node[head], rest)


def resolve_ref(datasets: dict, ref: str):
    """Resolve e.g. 'summary.totals.commits' against {dataset name: dataset}."""
    parts = ref.split(".")
    for take in (2, 1):
        if len(parts) > take - 1 and ".".join(parts[:take]) in datasets:
            node = datasets[".".join(parts[:take])]
            for key in parts[take:]:
                if not isinstance(node, dict) or key not in node:
                    return None
                node = node[key]
            return node
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/scenes/test_derived.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src tests
git commit -m "Add derived data access, field and reference resolution" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Dataset catalog and scene types

**Files:**
- Create: `src/team_wrapped/scenes/catalog.py`, `src/team_wrapped/scenes/scene_types.py`
- Create: `web/scene-types/message/type.yml`, `web/scene-types/stats/type.yml`, `web/scene-types/headcount/type.yml`
- Test: `tests/scenes/test_catalog_and_types.py`

**Interfaces:**
- Consumes: `LoadError` from `loader.py`; `docs/datasets.md`.
- Produces:
  - `load_catalog(path: Path) -> set[str]`: all dataset names in the catalog (`family.name` names found in the first column of the tables, plus `contributors`).
  - `SceneType(name: str, default_duration: float, required_params: list[str], dir: Path)`
  - `load_scene_types(web_dir: Path) -> dict[str, SceneType]`

- [ ] **Step 1: Write the failing tests**

`tests/scenes/test_catalog_and_types.py`:
```python
import pytest

from team_wrapped.scenes.catalog import load_catalog
from team_wrapped.scenes.loader import LoadError
from team_wrapped.scenes.scene_types import load_scene_types


def test_catalog_lists_planned_datasets(repo_root):
    names = load_catalog(repo_root / "docs" / "datasets.md")
    for expected in [
        "contributors",
        "summary.totals",
        "summary.activity_by_weekday",
        "summary.activity_by_hour",       # two names in one table cell
        "delivery_volume.lines",
        "review_collab.outcome_mix",
        "curiosities.biggest_pr_by_lines",
    ]:
        assert expected in names
    assert "nope.nothing" not in names


def test_catalog_from_small_file(tmp_path):
    f = tmp_path / "datasets.md"
    f.write_text("| Dataset | Fields |\n|---|---|\n| `a.b`, `a.c` | x |\n| `plain` | y |\n")
    assert load_catalog(f) == {"contributors", "a.b", "a.c"}


def test_scene_types_load_from_web(repo_root):
    types = load_scene_types(repo_root / "web")
    assert set(types) >= {"message", "stats", "headcount"}
    assert types["stats"].default_duration == 8.0
    assert types["stats"].required_params == ["items"]
    assert types["headcount"].required_params == ["groups"]
    assert types["message"].dir.name == "message"


def test_scene_type_name_must_match_folder(tmp_path):
    folder = tmp_path / "scene-types" / "stats"
    folder.mkdir(parents=True)
    (folder / "type.yml").write_text("name: other\ndefault_duration: 3\n")
    with pytest.raises(LoadError, match="does not match folder"):
        load_scene_types(tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/scenes/test_catalog_and_types.py -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'team_wrapped.scenes.catalog'`

- [ ] **Step 3: Write the implementation and the type definitions**

`src/team_wrapped/scenes/catalog.py`:
```python
"""Read dataset names from the catalog document (docs/datasets.md)."""
from __future__ import annotations

import re
from pathlib import Path

_NAME = re.compile(r"`([a-z_]+\.[a-z_]+)`")


def load_catalog(path) -> set[str]:
    """`family.name` names in the first column of the tables, plus `contributors`."""
    names = {"contributors"}
    for line in Path(path).read_text().splitlines():
        if line.startswith("|"):
            cells = line.split("|")
            if len(cells) > 1:
                names.update(_NAME.findall(cells[1]))
    return names
```

`src/team_wrapped/scenes/scene_types.py`:
```python
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
```

`web/scene-types/message/type.yml`:
```yaml
name: message
default_duration: 4
required_params: [text]
```

`web/scene-types/stats/type.yml`:
```yaml
name: stats
default_duration: 8
required_params: [items]
```

`web/scene-types/headcount/type.yml`:
```yaml
name: headcount
default_duration: 10
required_params: [groups]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/scenes/test_catalog_and_types.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src tests web
git commit -m "Add dataset catalog reader and scene type definitions" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Script validation

**Files:**
- Create: `src/team_wrapped/scenes/validate.py`
- Test: `tests/scenes/test_validate.py`

**Interfaces:**
- Consumes: `Script`, `Entry`, `Scene`, `load_script`, `load_scene` (loader); `DerivedData`, `has_field`, `resolve_ref` (derived); `load_catalog`; `SceneType`, `load_scene_types`.
- Produces:
  - `SceneResult(scene_id: str, status: str, problems: list[str], skipped: bool = False)`; `status` is `"supported"`, `"partial"` or `"unsupported"`.
  - `Report(script_id: str, results: list[SceneResult])` with property `ok` (no unsupported result unless it is `skipped`). `results` is in the same order as `script.scenes`.
  - `validate_script(script, scenes: dict[str, Scene], derived, catalog: set[str], scene_types: dict[str, SceneType]) -> Report`
  - `Resolved(script, scenes, derived, scene_types, report)`
  - `resolve_and_validate(script_id: str, repo_root, data_root) -> Resolved`: roots are `[repo_root, data_root]`, catalog is `repo_root/docs/datasets.md`, scene types are in `repo_root/web`.
  - `format_report(report: Report) -> str`

- [ ] **Step 1: Write the failing tests**

`tests/scenes/test_validate.py`:
```python
import json
from pathlib import Path

from team_wrapped.scenes.derived import DerivedData
from team_wrapped.scenes.loader import Entry, Scene, Script
from team_wrapped.scenes.scene_types import SceneType
from team_wrapped.scenes.validate import format_report, resolve_and_validate, validate_script

TYPES = {"stats": SceneType("stats", 8.0, ["items"], Path("."))}
CATALOG = {"summary.totals", "contributors"}


def make_data(tmp_path, partial=()):
    d = tmp_path / "derived"
    d.mkdir()
    (d / "summary.json").write_text(json.dumps(
        {"scopes": {"all": {"totals": {"commits": 5}}}}))
    (d / "meta.json").write_text(json.dumps({"partial_datasets": list(partial)}))
    return DerivedData(tmp_path)


def run(tmp_path, requires, params=None, entry=None, partial=(), catalog=CATALOG, type_="stats"):
    scene = Scene(id="s", type=type_, title="S", requires=requires,
                  params={"items": []} if params is None else params)
    script = Script(id="x", title="X", period=2026, scope="all", scenes=[entry or Entry(scene="s")])
    return validate_script(script, {"s": scene}, make_data(tmp_path, partial), catalog, TYPES)


REQ = [{"dataset": "summary.totals", "fields": ["commits"]}]


def test_supported(tmp_path):
    report = run(tmp_path, REQ)
    assert report.results[0].status == "supported"
    assert report.results[0].problems == []
    assert report.ok


def test_missing_field(tmp_path):
    report = run(tmp_path, [{"dataset": "summary.totals", "fields": ["commits", "nope"]}])
    assert report.results[0].status == "unsupported"
    assert "'summary.totals' is missing field 'nope'" in report.results[0].problems
    assert not report.ok


def test_dataset_not_in_catalog(tmp_path):
    report = run(tmp_path, [{"dataset": "made.up", "fields": []}])
    assert "dataset 'made.up' is not in the catalog" in report.results[0].problems


def test_no_data_for_scope(tmp_path):
    entry = Entry(scene="s", scope="alpha")  # scope key becomes group:alpha, which has no data
    report = run(tmp_path, REQ, entry=entry)
    assert "no data for 'summary.totals' in scope 'group:alpha'" in report.results[0].problems


def test_partial_allowed_and_not_allowed(tmp_path):
    (tmp_path / "a").mkdir()   # make_data creates derived/, so each run needs its own folder
    (tmp_path / "b").mkdir()
    allowed = [{"dataset": "summary.totals", "fields": ["commits"], "allow_partial": True}]
    report = run(tmp_path / "a", allowed, partial=["summary.totals"])
    assert report.results[0].status == "partial"
    assert report.ok
    report = run(tmp_path / "b", REQ, partial=["summary.totals"])
    assert report.results[0].status == "unsupported"
    assert any("partial" in p for p in report.results[0].problems)


def test_unknown_type_and_missing_param(tmp_path):
    report = run(tmp_path, REQ, type_="nope")
    assert "unknown scene type 'nope'" in report.results[0].problems
    report = run(tmp_path, REQ, params={})
    assert "missing required param 'items'" in report.results[0].problems


def test_value_refs_must_resolve_to_required_data(tmp_path):
    good = {"items": [{"label": "C", "value": "summary.totals.commits"}]}
    assert run(tmp_path, REQ, params=good).results[0].status == "supported"
    bad = {"items": [{"label": "C", "value": "summary.totals.nope"}]}
    report = run(tmp_path, REQ, params=bad)
    assert "value 'summary.totals.nope' does not resolve to required data" in report.results[0].problems


def test_skip_vs_fail(tmp_path):
    bad_req = [{"dataset": "summary.totals", "fields": ["nope"]}]
    skip = run(tmp_path, bad_req, entry=Entry(scene="s", on_missing_data="skip"))
    assert skip.results[0].status == "unsupported" and skip.results[0].skipped
    assert skip.ok
    fail = run(tmp_path, bad_req, entry=Entry(scene="s", on_missing_data="fail"))
    assert not fail.results[0].skipped and not fail.ok


def test_year_wrapped_on_sample(repo_root, sample_root):
    resolved = resolve_and_validate("year-wrapped", repo_root, sample_root)
    statuses = {r.scene_id: r.status for r in resolved.report.results}
    assert statuses == {"year-in-numbers": "partial", "how-many-of-us": "supported"}
    assert resolved.report.ok
    text = format_report(resolved.report)
    assert "year-in-numbers: partial" in text
    assert "how-many-of-us: supported" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/scenes/test_validate.py -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'team_wrapped.scenes.validate'`

- [ ] **Step 3: Write the implementation**

`src/team_wrapped/scenes/validate.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/scenes -v`
Expected: all tests pass (loader 7, derived 5, catalog and types 4, validate 9 = 25 passed)

- [ ] **Step 5: Commit**

```bash
git add src tests
git commit -m "Add script validation against derived data and catalog" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `validate-script` command

**Files:**
- Create: `src/team_wrapped/cli.py`, `src/team_wrapped/__main__.py`
- Test: `tests/scenes/test_cli_validate.py`

**Interfaces:**
- Consumes: `resolve_and_validate`, `format_report`, `LoadError`.
- Produces: `main(argv: list[str] | None = None) -> int`. Subcommand `validate-script <script> [--root .] [--data data]`. Exit code 0 if the report is ok, 1 if not, 2 on a load error. The `build` subcommand is added in Task 10.

- [ ] **Step 1: Write the failing tests**

`tests/scenes/test_cli_validate.py`:
```python
from team_wrapped.cli import main


def test_validate_year_wrapped_on_sample(repo_root, capsys):
    code = main(["validate-script", "year-wrapped", "--root", str(repo_root), "--data", "data-sample"])
    out = capsys.readouterr().out
    assert code == 0
    assert "year-in-numbers: partial" in out
    assert "how-many-of-us: supported" in out


def test_validate_reports_failure(tmp_path, repo_root, capsys):
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "datasets.md").write_text("| `summary.totals` | x |\n")
    (root / "web" / "scene-types" / "stats").mkdir(parents=True)
    (root / "web" / "scene-types" / "stats" / "type.yml").write_text(
        "name: stats\ndefault_duration: 8\nrequired_params: [items]\n")
    (root / "scenes").mkdir()
    (root / "scenes" / "s.yml").write_text(
        "id: s\ntype: stats\nrequires:\n  - {dataset: summary.totals, fields: [commits]}\nparams: {items: []}\n")
    (root / "scripts").mkdir()
    (root / "scripts" / "x.yml").write_text("id: x\nscenes:\n  - scene: s\n")
    (root / "data").mkdir()  # no derived data at all
    code = main(["validate-script", "x", "--root", str(root), "--data", "data"])
    out = capsys.readouterr().out
    assert code == 1
    assert "s: unsupported" in out
    assert "no data for 'summary.totals' in scope 'all'" in out


def test_validate_missing_script_exits_2(repo_root, capsys):
    code = main(["validate-script", "nope", "--root", str(repo_root), "--data", "data-sample"])
    assert code == 2
    assert "script 'nope' not found" in capsys.readouterr().err
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/scenes/test_cli_validate.py -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'team_wrapped.cli'`

- [ ] **Step 3: Write the implementation**

`src/team_wrapped/cli.py`:
```python
"""Command line entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .scenes.loader import LoadError
from .scenes.validate import format_report, resolve_and_validate


def _cmd_validate(args) -> int:
    root = Path(args.root)
    resolved = resolve_and_validate(args.script, root, root / args.data)
    print(format_report(resolved.report))
    return 0 if resolved.report.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="team-wrapped")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-script", help="check a script against the available data")
    validate.add_argument("script")
    validate.add_argument("--root", default=".", help="repository root (default: current directory)")
    validate.add_argument("--data", default="data", help="data folder under the root (data or data-sample)")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-script":
            return _cmd_validate(args)
    except LoadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0
```

`src/team_wrapped/__main__.py`:
```python
from .cli import main

raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/scenes -v`
Expected: 28 passed

- [ ] **Step 5: Run the command on the real sample**

Run: `PYTHONPATH=src python3 -m team_wrapped validate-script year-wrapped --data data-sample`
Expected output, exit code 0:
```
year-wrapped
  year-in-numbers: partial
  how-many-of-us: supported
```

- [ ] **Step 6: Commit**

```bash
git add src tests
git commit -m "Add validate-script command" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Front-end helpers (timing and presets)

**Files:**
- Create: `web/player/timing.js`, `web/presets/presets.js`
- Test: `tests-js/timing.test.js`, `tests-js/presets.test.js`

**Interfaces:**
- Produces, both files work in the browser (set `window.TeamWrapped.timing` / `window.TeamWrapped.presets`) and in Node (`module.exports`):
  - `timing.offsets(durations: number[]) -> {start, end}[]`
  - `timing.total(durations) -> number`
  - `timing.sceneAt(durations, seconds) -> {index, progress}` (seconds clamped to `[0, total]`; at the very end it returns the last scene with progress 1)
  - `timing.elapsed(durations, index, progress) -> seconds`
  - `presets.format(n: number) -> string` (en-US thousands separators)
  - `presets.lookup(data: object, ref: string) -> any | undefined` (same rules as the Python `resolve_ref`)
  - `presets.isPartial(partial: string[], ref: string) -> boolean`
  - `presets.fadeIn(tl, targets, at = 0, duration = 0.6)`
  - `presets.stagger(tl, targets, at = 0, each = 0.15, duration = 0.5)`
  - `presets.popIn(tl, targets, at = 0, each = 0.05, duration = 0.35)`
  - `presets.countUp(tl, el, to, at = 0, duration = 1.2)`
  - The four animation presets add tweens to the GSAP timeline `tl` and return it.

- [ ] **Step 1: Write the failing tests**

`tests-js/timing.test.js`:
```js
const test = require("node:test");
const assert = require("node:assert");
const timing = require("../web/player/timing.js");

test("offsets gives start and end of every scene", () => {
  assert.deepStrictEqual(timing.offsets([4, 6, 10]), [
    { start: 0, end: 4 },
    { start: 4, end: 10 },
    { start: 10, end: 20 },
  ]);
});

test("total adds durations", () => {
  assert.strictEqual(timing.total([4, 6, 10]), 20);
});

test("sceneAt finds the scene and the progress inside it", () => {
  const d = [4, 6, 10];
  assert.deepStrictEqual(timing.sceneAt(d, 0), { index: 0, progress: 0 });
  assert.deepStrictEqual(timing.sceneAt(d, 4), { index: 1, progress: 0 });
  assert.deepStrictEqual(timing.sceneAt(d, 7), { index: 1, progress: 0.5 });
});

test("sceneAt clamps before the start and after the end", () => {
  const d = [4, 6, 10];
  assert.deepStrictEqual(timing.sceneAt(d, -3), { index: 0, progress: 0 });
  assert.deepStrictEqual(timing.sceneAt(d, 99), { index: 2, progress: 1 });
  assert.deepStrictEqual(timing.sceneAt(d, 20), { index: 2, progress: 1 });
});

test("elapsed is the inverse of sceneAt", () => {
  const d = [4, 6, 10];
  assert.strictEqual(timing.elapsed(d, 1, 0.5), 7);
  assert.strictEqual(timing.elapsed(d, 0, 0), 0);
  assert.strictEqual(timing.elapsed(d, 2, 1), 20);
});
```

`tests-js/presets.test.js`:
```js
const test = require("node:test");
const assert = require("node:assert");
const presets = require("../web/presets/presets.js");

test("format uses thousands separators", () => {
  assert.strictEqual(presets.format(1240), "1,240");
  assert.strictEqual(presets.format(48200), "48,200");
  assert.strictEqual(presets.format(0), "0");
  assert.strictEqual(presets.format(-5), "-5");
});

test("lookup resolves family.name datasets and single-name datasets", () => {
  const data = { "summary.totals": { commits: 5 }, contributors: { total: 2, by_kind: { bot: 1 } } };
  assert.strictEqual(presets.lookup(data, "summary.totals.commits"), 5);
  assert.strictEqual(presets.lookup(data, "contributors.total"), 2);
  assert.strictEqual(presets.lookup(data, "contributors.by_kind.bot"), 1);
  assert.strictEqual(presets.lookup(data, "summary.totals.nope"), undefined);
  assert.strictEqual(presets.lookup(data, "other.thing.value"), undefined);
});

test("isPartial matches the dataset a reference points to", () => {
  const partial = ["delivery_volume.lines"];
  assert.strictEqual(presets.isPartial(partial, "delivery_volume.lines.total_net"), true);
  assert.strictEqual(presets.isPartial(partial, "summary.totals.commits"), false);
  assert.strictEqual(presets.isPartial([], "summary.totals.commits"), false);
});

test("animation presets add tweens to the timeline and return it", () => {
  const calls = [];
  const tl = {
    from: (t, v, at) => { calls.push(["from", v, at]); return tl; },
    to: (t, v, at) => { calls.push(["to", v, at]); return tl; },
  };
  assert.strictEqual(presets.fadeIn(tl, {}, 1, 0.5), tl);
  assert.strictEqual(presets.stagger(tl, [], 2), tl);
  assert.strictEqual(presets.popIn(tl, [], 3), tl);
  const el = { textContent: "" };
  assert.strictEqual(presets.countUp(tl, el, 100, 4, 1), tl);
  assert.strictEqual(el.textContent, "0");      // starts at zero
  assert.deepStrictEqual(calls.map((c) => c[0]), ["from", "from", "from", "to"]);
  assert.deepStrictEqual(calls.map((c) => c[2]), [1, 2, 3, 4]);
  // the count-up callback writes formatted numbers
  const to = calls[3][1];
  assert.strictEqual(to.v, 100);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests-js/`
Expected: FAIL with `Cannot find module '../web/player/timing.js'`

- [ ] **Step 3: Write the implementation**

`web/player/timing.js`:
```js
(function (root) {
  "use strict";

  function offsets(durations) {
    let t = 0;
    return durations.map((d) => {
      const start = t;
      t += d;
      return { start, end: t };
    });
  }

  function total(durations) {
    return durations.reduce((a, b) => a + b, 0);
  }

  function sceneAt(durations, seconds) {
    const t = Math.min(Math.max(seconds, 0), total(durations));
    const o = offsets(durations);
    for (let i = 0; i < o.length; i++) {
      if (t < o[i].end || i === o.length - 1) {
        const progress = durations[i] === 0 ? 1 : Math.min((t - o[i].start) / durations[i], 1);
        return { index: i, progress };
      }
    }
  }

  function elapsed(durations, index, progress) {
    return offsets(durations)[index].start + durations[index] * progress;
  }

  const api = { offsets, total, sceneAt, elapsed };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.TeamWrapped = root.TeamWrapped || {};
    root.TeamWrapped.timing = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
```

`web/presets/presets.js`:
```js
(function (root) {
  "use strict";

  const formatter = new Intl.NumberFormat("en-US");

  function format(n) {
    return formatter.format(n);
  }

  // Resolve "summary.totals.commits" against {dataset name: dataset}.
  // Dataset names are tried as the first two segments, then the first one.
  function lookup(data, ref) {
    const parts = ref.split(".");
    for (const take of [2, 1]) {
      const name = parts.slice(0, take).join(".");
      if (parts.length >= take && Object.prototype.hasOwnProperty.call(data, name)) {
        let node = data[name];
        for (const key of parts.slice(take)) {
          if (node === null || typeof node !== "object" || !(key in node)) return undefined;
          node = node[key];
        }
        return node;
      }
    }
    return undefined;
  }

  function isPartial(partial, ref) {
    return partial.some((name) => ref === name || ref.startsWith(name + "."));
  }

  function fadeIn(tl, targets, at = 0, duration = 0.6) {
    return tl.from(targets, { opacity: 0, y: 20, duration, ease: "power2.out" }, at);
  }

  function stagger(tl, targets, at = 0, each = 0.15, duration = 0.5) {
    return tl.from(targets, { opacity: 0, y: 24, duration, stagger: each, ease: "power2.out" }, at);
  }

  function popIn(tl, targets, at = 0, each = 0.05, duration = 0.35) {
    return tl.from(targets, { opacity: 0, scale: 0, duration, stagger: each, ease: "back.out(1.7)" }, at);
  }

  function countUp(tl, el, to, at = 0, duration = 1.2) {
    const state = { v: 0 };
    el.textContent = format(0);
    return tl.to(state, {
      v: to,
      duration,
      ease: "power1.out",
      onUpdate: () => { el.textContent = format(Math.round(state.v)); },
    }, at);
  }

  const api = { format, lookup, isPartial, fadeIn, stagger, popIn, countUp };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.TeamWrapped = root.TeamWrapped || {};
    root.TeamWrapped.presets = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test tests-js/`
Expected: all tests pass (`# pass 9`, `# fail 0`)

- [ ] **Step 5: Commit**

```bash
git add web tests-js
git commit -m "Add front-end timing helpers and animation presets" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Scene renderers

**Files:**
- Create: `web/scene-types/message/render.js`, `web/scene-types/stats/render.js`, `web/scene-types/headcount/render.js`

**Interfaces:**
- Consumes: the `ctx` object `{container, data, params, duration, partial, scope, period, gsap, presets}` that the player passes (Task 9); `presets` from Task 6. `data` is `{dataset name: dataset}` for the scene's `requires`.
- Produces: each file has exactly one `export default { render(ctx) }` and no `import` (the build rewrites it into a registry assignment, Task 10). `render` returns a GSAP timeline.
- CSS class names these renderers use (styled in Task 9): `tw-message`, `tw-stats`, `tw-stat`, `tw-stat-value`, `tw-stat-label`, `tw-stat-partial`, `tw-group`, `tw-group-count`, `tw-group-label`, `tw-faces`, `tw-face`.

These renderers build DOM and timelines, so they are verified in the browser in Task 11, not by unit tests. The pure helpers they depend on are tested in Task 6.

- [ ] **Step 1: Write the message renderer**

`web/scene-types/message/render.js`:
```js
export default {
  render(ctx) {
    const { container, params, gsap, presets } = ctx;
    const heading = document.createElement("h1");
    heading.className = "tw-message";
    heading.textContent = params.text;
    container.appendChild(heading);
    const tl = gsap.timeline();
    presets.fadeIn(tl, heading, 0.2, 0.8);
    return tl;
  },
};
```

- [ ] **Step 2: Write the stats renderer**

`web/scene-types/stats/render.js`:
```js
export default {
  render(ctx) {
    const { container, data, params, partial, gsap, presets } = ctx;
    const grid = document.createElement("div");
    grid.className = "tw-stats";
    const cards = [];
    const tl = gsap.timeline();

    params.items.forEach((item, i) => {
      const card = document.createElement("div");
      card.className = "tw-stat";
      const value = document.createElement("div");
      value.className = "tw-stat-value";
      const label = document.createElement("div");
      label.className = "tw-stat-label";
      label.textContent = item.label;
      card.append(value, label);

      const raw = presets.lookup(data, item.value);
      if (typeof raw === "number") {
        presets.countUp(tl, value, raw, 0.3 + i * 0.15, 1.2);
      } else {
        value.textContent = "–";
      }
      if (presets.isPartial(partial, item.value)) {
        const badge = document.createElement("div");
        badge.className = "tw-stat-partial";
        badge.textContent = "partial data";
        card.append(badge);
      }
      grid.append(card);
      cards.push(card);
    });

    container.append(grid);
    presets.stagger(tl, cards, 0, 0.15, 0.5);
    return tl;
  },
};
```

- [ ] **Step 3: Write the headcount renderer**

`web/scene-types/headcount/render.js`:
```js
export default {
  render(ctx) {
    const { container, data, params, gsap, presets } = ctx;
    const people = (data.contributors && data.contributors.list) || [];
    const tl = gsap.timeline();
    let at = 0.2;

    params.groups.forEach((group) => {
      const members = people.filter((p) => group.kinds.includes(p.kind));

      const section = document.createElement("section");
      section.className = "tw-group";
      const count = document.createElement("div");
      count.className = "tw-group-count";
      const label = document.createElement("div");
      label.className = "tw-group-label";
      label.textContent = group.label;
      const faces = document.createElement("div");
      faces.className = "tw-faces";

      const imgs = members.map((p) => {
        const img = document.createElement("img");
        img.className = "tw-face";
        img.src = p.avatar_file;
        img.alt = p.login || "contributor without a GitHub account";
        faces.append(img);
        return img;
      });

      section.append(count, label, faces);
      container.append(section);

      // Cap the total pop-in time so large teams do not overrun the scene.
      const each = Math.min(0.06, 2 / Math.max(members.length, 1));
      presets.fadeIn(tl, section, at, 0.5);
      presets.countUp(tl, count, members.length, at, 1.0);
      presets.popIn(tl, imgs, at + 0.4, each);
      at += 0.4 + each * members.length + 0.8;
    });

    return tl;
  },
};
```

- [ ] **Step 4: Check each file has exactly one `export default` and no `import`**

Run: `grep -c "export default" web/scene-types/*/render.js; grep -n "^\s*import " web/scene-types/*/render.js || echo "no imports"`
Expected: each file prints `:1`, then `no imports`

- [ ] **Step 5: Commit**

```bash
git add web
git commit -m "Add message, stats and headcount scene renderers" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Vendor GSAP

**Files:**
- Create: `web/vendor/gsap.min.js`, `web/vendor/GSAP-LICENSE.md`

**Interfaces:**
- Produces: `web/vendor/gsap.min.js` (defines `window.gsap`) and the licence text that must ship with it. `build` (Task 10) refuses to run without `gsap.min.js`.

This step downloads a file from the npm registry, so **ask the user for permission before running it**, and state the source (`gsap` on npm) and that it is about 70 KB. The sandbox needs `registry.npmjs.org` allowed.

- [ ] **Step 1: Download the package and list its files**

```bash
cd "$TMPDIR" && npm pack gsap && tar -tzf gsap-*.tgz | grep -E "dist/gsap\.min\.js$|LICEN[CS]E"
```
Expected: a line `package/dist/gsap.min.js` and one or more licence file names (for example `package/LICENSE`).

- [ ] **Step 2: Copy the library and its licence into the repo**

Use the licence file name printed in Step 1 (shown here as `LICENSE`; adjust if different).
```bash
cd "$TMPDIR" && tar -xzf gsap-*.tgz package/dist/gsap.min.js package/LICENSE
mkdir -p /Users/rares.rusu/git/team-wrapped/web/vendor
cp package/dist/gsap.min.js /Users/rares.rusu/git/team-wrapped/web/vendor/gsap.min.js
cp package/LICENSE /Users/rares.rusu/git/team-wrapped/web/vendor/GSAP-LICENSE.md
```

- [ ] **Step 3: Verify the files**

Run: `cd /Users/rares.rusu/git/team-wrapped && test -s web/vendor/gsap.min.js && head -c 300 web/vendor/gsap.min.js && echo && head -5 web/vendor/GSAP-LICENSE.md`
Expected: the first output shows a GSAP banner comment (contains `GSAP`), and the licence file has readable text.

- [ ] **Step 4: Ask the user to read the licence**

Tell the user: the spec requires them to confirm the current GSAP licence terms before a public release. Point them at `web/vendor/GSAP-LICENSE.md`. Do not proceed to commit until they have said it is acceptable to commit it.

- [ ] **Step 5: Commit**

```bash
git add web/vendor
git commit -m "Vendor GSAP with its licence" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Player page (template, styles, controller)

**Files:**
- Create: `web/player/index.template.html`, `web/player/player.css`, `web/player/player.js`

**Interfaces:**
- Consumes: `window.gsap` (Task 8), `TeamWrapped.timing` and `TeamWrapped.presets` (Task 6), `TeamWrapped.sceneTypes[type].render(ctx)` (Task 7, registered by the build), and the embedded JSON in `<script type="application/json" id="tw-data">`:
```json
{
  "script": {"id": "...", "title": "...", "period": 2026, "scope": "all",
             "transition": "fade", "music": {"src": "assets/music/x.mp3", "volume": 0.5, "loop": true} },
  "scenes": [{"id": "...", "title": "...", "type": "stats", "duration": 8.0,
              "params": {}, "data": {}, "partial": [], "scope": "all", "transition": "fade"}]
}
```
  (`music` is `null` when the script has no music.)
- Produces: template markers the build replaces: `{{TITLE}}`, `<!--TW_DATA-->` (the JSON script tag) and `<!--TW_RENDERERS-->` (an inline script registering the renderers). A debug handle `window.TeamWrapped.player` with `{state, scenes, durations, enter(index, play), setPlaying(bool)}` for browser checks.

This is browser code, verified in Task 11.

- [ ] **Step 1: Write the page template**

`web/player/index.template.html`:
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{TITLE}}</title>
  <link rel="stylesheet" href="assets/player.css">
</head>
<body>
  <div id="tw-stage"></div>

  <div id="tw-start" class="tw-overlay">
    <h1 id="tw-start-title">{{TITLE}}</h1>
    <button id="tw-play-btn" type="button">Play</button>
  </div>

  <div id="tw-end" class="tw-overlay" hidden>
    <button id="tw-replay-btn" type="button">Replay</button>
  </div>

  <div id="tw-controls">
    <button id="tw-toggle" type="button">Pause</button>
    <div id="tw-progress"></div>
    <span id="tw-scene-title"></span>
    <button id="tw-mute" type="button">Mute</button>
  </div>

  <script src="assets/vendor/gsap.min.js"></script>
  <script src="assets/timing.js"></script>
  <script src="assets/presets.js"></script>
  <!--TW_DATA-->
  <!--TW_RENDERERS-->
  <script src="assets/player.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write the styles**

`web/player/player.css`:
```css
[hidden] { display: none !important; }

* { box-sizing: border-box; }

html, body { margin: 0; height: 100%; background: #0f1115; color: #f2f3f5;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif; overflow: hidden; }

#tw-stage { position: fixed; inset: 0; }

.tw-scene { position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; padding: 2rem 2rem 5rem; text-align: center; }

.tw-overlay { position: fixed; inset: 0; z-index: 10; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 2rem; background: #0f1115; }
#tw-start-title { font-size: clamp(2rem, 6vw, 4rem); margin: 0; }
.tw-overlay button { font-size: 1.5rem; padding: 0.8rem 2.5rem; border-radius: 999px;
  border: 0; cursor: pointer; background: #f2f3f5; color: #0f1115; }

#tw-controls { position: fixed; left: 0; right: 0; bottom: 0; z-index: 5; display: flex;
  align-items: center; gap: 1rem; padding: 0.8rem 1.2rem; background: rgba(0, 0, 0, 0.55); }
body:not(.tw-started) #tw-controls { display: none; }
#tw-controls button { background: transparent; color: inherit; border: 1px solid #555;
  border-radius: 6px; padding: 0.3rem 0.8rem; cursor: pointer; min-width: 4.5rem; }
#tw-scene-title { font-size: 0.85rem; opacity: 0.7; min-width: 9rem; }

#tw-progress { flex: 1; display: flex; gap: 4px; height: 22px; cursor: pointer; touch-action: none; }
.tw-seg { position: relative; padding: 0; border: 0; background: #3a3d44; border-radius: 3px;
  overflow: hidden; cursor: pointer; }
.tw-seg-fill { position: absolute; left: 0; top: 0; bottom: 0; width: 0; background: #f2f3f5; }
.tw-seg.tw-current { outline: 2px solid #8ab4ff; }

.tw-message { font-size: clamp(2rem, 7vw, 5rem); margin: 0; }

.tw-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 1.5rem; width: min(70rem, 100%); }
.tw-stat-value { font-size: clamp(2rem, 5vw, 3.5rem); font-weight: 700; font-variant-numeric: tabular-nums; }
.tw-stat-label { opacity: 0.75; margin-top: 0.3rem; }
.tw-stat-partial { margin-top: 0.4rem; font-size: 0.75rem; color: #e6b450; }

.tw-group { margin: 1rem 0; }
.tw-group-count { font-size: clamp(2.5rem, 6vw, 4.5rem); font-weight: 700; font-variant-numeric: tabular-nums; }
.tw-group-label { opacity: 0.75; margin-bottom: 0.8rem; }
.tw-faces { display: flex; flex-wrap: wrap; justify-content: center; gap: 0.4rem; max-width: 60rem; }
.tw-face { width: 3rem; height: 3rem; border-radius: 50%; object-fit: cover; background: #3a3d44; }
```

- [ ] **Step 3: Write the controller**

`web/player/player.js`:
```js
(function () {
  "use strict";

  const TW = window.TeamWrapped;
  const gsap = window.gsap;
  const timing = TW.timing;
  const payload = JSON.parse(document.getElementById("tw-data").textContent);
  const scenes = payload.scenes;
  const durations = scenes.map((s) => s.duration);
  const music = payload.script.music;
  const MUTE_KEY = "tw-muted";
  const FADE = 0.4;

  const $ = (id) => document.getElementById(id);
  const els = {
    stage: $("tw-stage"), start: $("tw-start"), end: $("tw-end"),
    playBtn: $("tw-play-btn"), replayBtn: $("tw-replay-btn"),
    toggle: $("tw-toggle"), progress: $("tw-progress"),
    mute: $("tw-mute"), sceneTitle: $("tw-scene-title"),
  };

  const state = { started: false, playing: false, index: 0, tl: null, el: null, scrubbing: false };

  function store(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(key);
      localStorage.setItem(key, value);
    } catch (e) { /* storage can be blocked on file:// in some browsers */ }
    return null;
  }

  // ---- music ---------------------------------------------------------
  let audio = null;
  if (music) {
    audio = new Audio(music.src);
    audio.loop = music.loop !== false;
    audio.volume = 0;
    audio.muted = store(MUTE_KEY) === "1";
  } else {
    els.mute.hidden = true;
  }

  function playAudio() {
    if (!audio) return;
    audio.play().catch(() => {});
    gsap.to(audio, { volume: music.volume != null ? music.volume : 0.5, duration: 2, overwrite: true });
  }
  function pauseAudio() { if (audio) audio.pause(); }
  function toggleMute() {
    if (!audio) return;
    audio.muted = !audio.muted;
    store(MUTE_KEY, audio.muted ? "1" : "0");
    refresh();
  }

  // ---- progress line -------------------------------------------------
  const segs = scenes.map((scene, i) => {
    const seg = document.createElement("button");
    seg.type = "button";
    seg.className = "tw-seg";
    seg.dataset.index = String(i);
    seg.style.flex = String(scene.duration);
    seg.title = scene.title;
    seg.setAttribute("aria-label", scene.title);
    const fill = document.createElement("div");
    fill.className = "tw-seg-fill";
    seg.append(fill);
    els.progress.append(seg);
    return { seg, fill };
  });

  function refresh() {
    els.toggle.textContent = state.playing ? "Pause" : "Play";
    if (audio) els.mute.textContent = audio.muted ? "Unmute" : "Mute";
    els.sceneTitle.textContent = scenes[state.index] ? scenes[state.index].title : "";
    segs.forEach((s, i) => s.seg.classList.toggle("tw-current", i === state.index));
  }

  gsap.ticker.add(() => {
    if (!state.started || !state.tl) return;
    const progress = state.tl.progress();
    segs.forEach((s, i) => {
      const pct = i < state.index ? 100 : i === state.index ? progress * 100 : 0;
      s.fill.style.width = pct + "%";
    });
  });

  // ---- scenes --------------------------------------------------------
  function enter(index, play) {
    els.end.hidden = true;
    if (state.tl) state.tl.kill();
    const old = state.el;

    const scene = scenes[index];
    const renderer = TW.sceneTypes[scene.type];
    const el = document.createElement("section");
    el.className = "tw-scene";
    els.stage.append(el);

    const inner = renderer.render({
      container: el, data: scene.data, params: scene.params, duration: scene.duration,
      partial: scene.partial, scope: scene.scope, period: payload.script.period,
      gsap, presets: TW.presets,
    });

    // Pad the scene to exactly its duration so progress and hold time are predictable.
    const tl = gsap.timeline({
      paused: true,
      onComplete: () => (index < scenes.length - 1 ? enter(index + 1, true) : finish()),
    });
    tl.add(inner, 0);
    tl.to({}, { duration: scene.duration }, 0);

    state.index = index;
    state.tl = tl;
    state.el = el;
    state.playing = !!play;

    // Cross-fade between scenes (the only transition implemented so far).
    gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: FADE });
    if (old) gsap.to(old, { opacity: 0, duration: FADE, onComplete: () => old.remove() });

    if (play) tl.play();
    refresh();
  }

  function finish() {
    state.playing = false;
    pauseAudio();
    els.end.hidden = false;
    refresh();
  }

  function setPlaying(playing) {
    if (!state.tl) return;
    state.playing = playing;
    if (playing) { state.tl.play(); playAudio(); } else { state.tl.pause(); pauseAudio(); }
    refresh();
  }

  function start() {
    state.started = true;
    document.body.classList.add("tw-started");
    els.start.hidden = true;
    enter(0, true);
    playAudio();
  }

  // ---- events --------------------------------------------------------
  els.playBtn.addEventListener("click", start);
  els.replayBtn.addEventListener("click", () => { enter(0, true); playAudio(); });
  els.toggle.addEventListener("click", () => setPlaying(!state.playing));
  els.mute.addEventListener("click", toggleMute);

  function scrubTo(ev) {
    const rect = segs[state.index].seg.getBoundingClientRect();
    const f = Math.min(Math.max((ev.clientX - rect.left) / rect.width, 0), 1);
    state.tl.progress(f);
  }

  els.progress.addEventListener("pointerdown", (ev) => {
    const seg = ev.target.closest(".tw-seg");
    if (!seg || !state.started) return;
    const i = Number(seg.dataset.index);
    if (i === state.index && els.end.hidden) {
      state.scrubbing = true;
      els.progress.setPointerCapture(ev.pointerId);
      scrubTo(ev);
    } else {
      enter(i, state.playing);
    }
  });
  els.progress.addEventListener("pointermove", (ev) => { if (state.scrubbing) scrubTo(ev); });
  els.progress.addEventListener("pointerup", () => { state.scrubbing = false; });

  document.addEventListener("keydown", (ev) => {
    if (!state.started) return;
    if (ev.code === "Space") { ev.preventDefault(); setPlaying(!state.playing); }
    else if (ev.code === "ArrowRight") enter(Math.min(state.index + 1, scenes.length - 1), state.playing);
    else if (ev.code === "ArrowLeft") enter(Math.max(state.index - 1, 0), state.playing);
    else if (ev.key === "m" || ev.key === "M") toggleMute();
  });

  TW.player = { state, scenes, durations, enter, setPlaying };
  refresh();
})();
```

- [ ] **Step 4: Syntax-check the controller**

Run: `node --check web/player/player.js && echo ok`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add web
git commit -m "Add player page template, styles and controller" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: `build` command

**Files:**
- Create: `src/team_wrapped/scenes/build.py`
- Modify: `src/team_wrapped/cli.py`
- Modify: `scenes/year-in-numbers.yml`, `scenes/how-many-of-us.yml` (add `title`)
- Modify: `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md` (section 12 and 13 notes)
- Test: `tests/scenes/test_build.py`

**Interfaces:**
- Consumes: `resolve_and_validate`, `Resolved`; the template and assets from Tasks 6 to 9.
- Produces:
  - `BuildError(message, report=None)`; `report` holds the failing `Report` when validation failed.
  - `BuildResult(out_dir: Path, index: Path, skipped: list[str])`
  - `transform_renderer(name: str, source: str) -> str`: rewrites `export default` into `TeamWrapped.sceneTypes["<name>"] = ` and rejects `import` lines or a source without exactly one `export default`.
  - `build(script_id: str, repo_root, data_root, out_root) -> BuildResult`: writes `<out_root>/<script_id>/index.html`, `assets/` (player files, `vendor/`, optional `music/`) and `avatars/` (copied from `<data_root>/avatars`, so the relative `avatar_file` paths keep working).
  - CLI: `build <script> [--root .] [--data data] [--out dist]`; exit code 0 on success, 1 on `BuildError`, 2 on `LoadError`.

- [ ] **Step 1: Write the failing tests**

`tests/scenes/test_build.py`:
```python
import json
import re
import shutil

import pytest

from team_wrapped.cli import main
from team_wrapped.scenes.build import BuildError, build, transform_renderer


def read_payload(index):
    html = index.read_text()
    match = re.search(r'<script type="application/json" id="tw-data">(.*?)</script>', html, re.S)
    return json.loads(match.group(1).replace("<\\/", "</"))


def sample_copy(sample_root, tmp_path):
    data = tmp_path / "data"
    shutil.copytree(sample_root, data)
    return data


def test_build_year_wrapped_on_sample(repo_root, sample_root, tmp_path):
    result = build("year-wrapped", repo_root, sample_root, tmp_path / "dist")
    out = tmp_path / "dist" / "year-wrapped"
    assert result.index == out / "index.html"
    assert result.skipped == []
    for name in ["player.css", "timing.js", "presets.js", "player.js", "vendor/gsap.min.js"]:
        assert (out / "assets" / name).is_file(), name
    assert (out / "avatars" / "ada-dev.png").is_file()

    payload = read_payload(result.index)
    assert [s["id"] for s in payload["scenes"]] == ["year-in-numbers", "how-many-of-us"]
    assert [s["duration"] for s in payload["scenes"]] == [8.0, 10.0]
    assert payload["scenes"][0]["partial"] == ["delivery_volume.lines"]
    assert payload["scenes"][1]["partial"] == []
    assert payload["scenes"][0]["data"]["summary.totals"]["commits"] == 1240
    assert payload["script"]["music"] is None

    html = result.index.read_text()
    assert 'TeamWrapped.sceneTypes["stats"]' in html
    assert 'TeamWrapped.sceneTypes["headcount"]' in html
    assert 'TeamWrapped.sceneTypes["message"]' not in html   # only used types are inlined
    assert "export default" not in html


def test_build_fails_when_a_scene_is_unsupported(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    (data / "derived" / "delivery_volume.json").unlink()
    with pytest.raises(BuildError) as error:
        build("year-wrapped", repo_root, data, tmp_path / "dist")
    assert error.value.report is not None
    assert not error.value.report.ok


def test_build_skips_scenes_marked_skip(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    (data / "derived" / "delivery_volume.json").unlink()
    (data / "scripts").mkdir()
    (data / "scripts" / "skipper.yml").write_text(
        "id: skipper\ntitle: Skipper\nscope: all\nscenes:\n"
        "  - scene: year-in-numbers\n    on_missing_data: skip\n"
        "  - scene: how-many-of-us\n")
    result = build("skipper", repo_root, data, tmp_path / "dist")
    assert result.skipped == ["year-in-numbers"]
    assert [s["id"] for s in read_payload(result.index)["scenes"]] == ["how-many-of-us"]


def test_build_copies_local_music(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    (data / "assets").mkdir()
    (data / "assets" / "theme.mp3").write_bytes(b"fake")
    (data / "scripts").mkdir()
    (data / "scripts" / "tune.yml").write_text(
        "id: tune\nscope: all\nscenes:\n  - scene: how-many-of-us\n"
        "music: {file: theme.mp3, volume: 0.3}\n")
    result = build("tune", repo_root, data, tmp_path / "dist")
    music = read_payload(result.index)["script"]["music"]
    assert music == {"src": "assets/music/theme.mp3", "volume": 0.3, "loop": True}
    assert (tmp_path / "dist" / "tune" / "assets" / "music" / "theme.mp3").read_bytes() == b"fake"


def test_build_accepts_music_url_and_rejects_missing_file(repo_root, sample_root, tmp_path):
    data = sample_copy(sample_root, tmp_path)
    (data / "scripts").mkdir()
    (data / "scripts" / "url.yml").write_text(
        "id: url\nscope: all\nscenes:\n  - scene: how-many-of-us\nmusic: {file: 'https://example.com/a.mp3'}\n")
    (data / "scripts" / "gone.yml").write_text(
        "id: gone\nscope: all\nscenes:\n  - scene: how-many-of-us\nmusic: {file: nothere.mp3}\n")
    result = build("url", repo_root, data, tmp_path / "dist")
    assert read_payload(result.index)["script"]["music"]["src"] == "https://example.com/a.mp3"
    with pytest.raises(BuildError, match="nothere.mp3"):
        build("gone", repo_root, data, tmp_path / "dist")


def test_transform_renderer():
    out = transform_renderer("x", "export default { render() {} };")
    assert out.startswith('TeamWrapped.sceneTypes["x"] = ')
    assert "export default" not in out
    with pytest.raises(BuildError, match="must not use import"):
        transform_renderer("x", 'import a from "./a.js";\nexport default {};')
    with pytest.raises(BuildError, match="exactly one"):
        transform_renderer("x", "export default {};\nexport default {};")
    with pytest.raises(BuildError, match="exactly one"):
        transform_renderer("x", "const a = 1;")


def test_cli_build(repo_root, tmp_path, capsys):
    code = main(["build", "year-wrapped", "--root", str(repo_root), "--data", "data-sample",
                 "--out", str(tmp_path / "dist")])
    assert code == 0
    assert (tmp_path / "dist" / "year-wrapped" / "index.html").is_file()
    assert "index.html" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/scenes/test_build.py -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'team_wrapped.scenes.build'`

- [ ] **Step 3: Write the build module**

`src/team_wrapped/scenes/build.py`:
```python
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
```

- [ ] **Step 4: Add the `build` subcommand to the CLI**

In `src/team_wrapped/cli.py`, replace the imports block and the functions below it so the file reads:
```python
"""Command line entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .scenes.build import BuildError, build
from .scenes.loader import LoadError
from .scenes.validate import format_report, resolve_and_validate


def _cmd_validate(args) -> int:
    root = Path(args.root)
    resolved = resolve_and_validate(args.script, root, root / args.data)
    print(format_report(resolved.report))
    return 0 if resolved.report.ok else 1


def _cmd_build(args) -> int:
    root = Path(args.root)
    try:
        result = build(args.script, root, root / args.data, root / args.out)
    except BuildError as error:
        print(f"error: {error}", file=sys.stderr)
        if error.report is not None:
            print(format_report(error.report), file=sys.stderr)
        return 1
    for scene_id in result.skipped:
        print(f"skipped (unsupported): {scene_id}")
    print(f"built {result.index}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="team-wrapped")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in [
        ("validate-script", "check a script against the available data"),
        ("build", "build a self-contained HTML page for a script"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("script")
        p.add_argument("--root", default=".", help="repository root (default: current directory)")
        p.add_argument("--data", default="data", help="data folder under the root (data or data-sample)")
        if name == "build":
            p.add_argument("--out", default="dist", help="output folder under the root (default: dist)")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-script":
            return _cmd_validate(args)
        return _cmd_build(args)
    except LoadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
```

- [ ] **Step 5: Add scene titles for the progress line**

`scenes/year-in-numbers.yml`: add a line `title: The year in numbers` directly under `id: year-in-numbers`.

`scenes/how-many-of-us.yml`: add a line `title: How many of us` directly under `id: how-many-of-us`.

- [ ] **Step 6: Run all Python tests**

Run: `python3 -m pytest -v`
Expected: all pass (35 passed: loader 7, derived 5, catalog and types 4, validate 9, cli validate 3, build 7)

- [ ] **Step 7: Note the two deliberate deviations in the spec**

In `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`, section 13, find the bullet that begins with `` - `render.js`: `export default { render(ctx) }` `` and append this sentence to the end of that bullet:
```
The build rewrites the single `export default` into a registry assignment and rejects `import` lines, because pages open from disk and browsers block module imports on `file://`.
```
In the same section, find the bullet that begins with `` - `type.yml`: `` and append:
```
In the first version the params schema is the list `required_params`; `validate-script` checks that each is present.
```
In section 12, in the **Scene** list, append a bullet:
```
- A scene file may set an optional `title`, which the player shows on the progress line (the default is the `id`).
```

- [ ] **Step 8: Commit**

```bash
git add src tests scenes docs
git commit -m "Add build command that writes a self-contained player page" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Browser verification and README

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: the built page from `build` (Task 10).

The player has no automated browser test in this plan, so this task verifies it by hand. Use the in-app browser (`preview_start` with a `url`) or any desktop browser. Opening `dist/year-wrapped/index.html` from disk works because everything is embedded. If the in-app browser refuses `file://`, serve the folder with `python3 -m http.server 8000 --directory dist/year-wrapped` and open `http://localhost:8000/`.

- [ ] **Step 1: Build the page from the sample data**

Run: `PYTHONPATH=src python3 -m team_wrapped build year-wrapped --data data-sample`
Expected: `built dist/year-wrapped/index.html`

- [ ] **Step 2: Check the start screen and Play**

Open the page. Expected: a dark start screen with the title "Year Wrapped" and a Play button; no control bar yet. Click Play. Expected: the control bar appears, the first scene ("The year in numbers") fades in with seven stat cards counting up (commits 1,240; merged pull requests 310; reviews 540; comments 1,180; lines added 48,200; lines deleted 21,350; net lines 26,850). The three lines figures show a "partial data" note.

- [ ] **Step 3: Check pause, progress line and jumping**

- Click Pause: animation freezes, the button reads Play. Click Play: it resumes.
- The progress line shows two segments, the first about 8/18 of the width and the second about 10/18, titled on hover.
- Click the second segment: the headcount scene appears. Click the first segment: it returns to the start of scene one.
- Drag inside the current segment: the count-ups scrub forwards and backwards.
- Press Space (pause/play), the right and left arrow keys (next/previous scene).

- [ ] **Step 4: Check the headcount scene**

Expected: a "Humans" count of 10 with ten round avatar images popping in, then a "Robots" count of 3 with three grey avatars. After the scene ends, the end screen with a Replay button shows; Replay restarts from scene one.

- [ ] **Step 5: Check durations and errors from the page itself**

In the browser console (or the in-app `javascript_tool`):
```js
TeamWrapped.player.durations
```
Expected: `[8, 10]`. Expected: no errors in the console.

- [ ] **Step 6: Check music and mute**

Create a throwaway test track and script that are not committed (both live in the git-ignored `data/` folder):
```bash
mkdir -p data/assets data/scripts data/derived
cp -R data-sample/derived/. data/derived/ && cp -R data-sample/avatars data/avatars
cp /path/to/any-short-audio-file.mp3 data/assets/theme.mp3
printf 'id: year-wrapped\ntitle: Year Wrapped\nperiod: 2026\nscope: all\nmusic: {file: theme.mp3, volume: 0.3}\nscenes:\n  - scene: year-in-numbers\n  - scene: how-many-of-us\n' > data/scripts/year-wrapped.yml
PYTHONPATH=src python3 -m team_wrapped build year-wrapped --data data
```
Open the new page. Expected: the Mute button is shown; music fades in on Play, pauses with the script, keeps playing when jumping between scenes, Mute silences it, and the mute choice survives a page reload. Then remove the test data: `rm -rf data dist`.

Ask the user for a short audio file or use one of their own; do not commit audio.

- [ ] **Step 7: Write the README**

`README.md`:
````markdown
# team-wrapped

Collect GitHub activity for a set of repositories and play it back as a "wrapped" page: scenes linked by a script, with animation and background music.

Status: the scene, validation and player layers work on the sample data. The collector and aggregator are not built yet; see `docs/superpowers/`.

## Try it on the sample data

```bash
pip install pyyaml pytest
PYTHONPATH=src python3 -m team_wrapped validate-script year-wrapped --data data-sample
PYTHONPATH=src python3 -m team_wrapped build year-wrapped --data data-sample
```
Then open `dist/year-wrapped/index.html` in a browser.

## Layout

- `scenes/`, `scripts/`: shared scene and script definitions.
- `web/`: the player, scene types, animation presets and vendored GSAP.
- `docs/datasets.md`: the catalog of datasets a scene may require.
- `data-sample/`: dummy data in the same layout as your private `data/` folder.
- `data/` and `dist/`: private, git-ignored. Put your own derived data, scenes, scripts and music in `data/`.

## Tests

```bash
python3 -m pytest
node --test tests-js/
```

The design is in `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`.
````

- [ ] **Step 8: Run the full test suites and check nothing private is tracked**

Run: `python3 -m pytest -q && node --test tests-js/ 2>&1 | tail -4 && git status --short && git ls-files | grep -E "^(data|dist)/" || echo "no private paths tracked"`
Expected: pytest passes, node tests `# fail 0`, a clean `git status` apart from `README.md`, and `no private paths tracked`.

- [ ] **Step 9: Commit**

```bash
git add README.md
git commit -m "Add README with usage on the sample data" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Not in this plan

- **Plan 2 (aggregator)** and **Plan 3 (collector)**.
- A headless-browser smoke test and CI wiring (the CI check that `data/` and `dist/` are untracked, and `build` on `data-sample` in CI). Task 11 verifies by hand.
- Scene types `curiosity` and media (image, video); they come with the scenes that need them.
- Transitions other than the cross-fade. The `transition` field is stored and passed to the page but the player always fades.
- `validate-script` naming the metric that would produce a missing dataset (needs a dataset-to-metric map).
- Time-bucketed dataset series (the first scene that needs one settles the shape).
