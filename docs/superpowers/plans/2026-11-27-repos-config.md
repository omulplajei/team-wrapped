# Repository Config and Derived Repos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read a private `data/config.yml` (organisation, repositories, groups) and derive from it the `repos.touched` dataset for the repositories scene, and let that scene show an optional footnote.

**Architecture:** A generic `config.py` loads and validates the collection config (spec section 4, the subset needed now). A pure `derive_repos` turns a config into the `repos.json` derived file (spec section 7.6), exposed as a new CLI command `derive-repos`. Until the aggregator exists every configured repository counts as touched, and the file is marked `"basis": "configuration"`. The `repogrid` scene type gets an optional `footnote`. Nothing org-specific is committed: the real config, the importer from org-config and the footnote wording live in the git-ignored `data/`.

**Tech Stack:** Python 3.11+ (PyYAML, pytest), classic-script JavaScript renderer tested with `node --test`.

Builds on the earlier plans (all on `main`).

## Global Constraints

- Nothing project-specific is committed: no real org, repo or capability names, in code, tests, samples or docs (use `sample-org`, `sample-*` repos, groups `alpha` and `beta`). The real `data/config.yml` is private and git-ignored.
- Config keys follow spec section 4. Known keys: `org`, `repos`, `groups`, `since`, `until`, `metrics`, `commit_branches`, `bot_patterns`, `aliases`, `timezone`, `curiosities`, `avatars`, `reviewer_pairs`. Only `org`, `repos`, `groups`, `since`, `until` are validated now; the others are accepted untouched until the collector uses them; any other key is an error.
- Validation: `org` matches `[A-Za-z0-9-]+`; `repos` is a non-empty list of unique names matching `[A-Za-z0-9._-]+`; `groups` is an optional mapping of names matching `[A-Za-z0-9][A-Za-z0-9_.-]*` to non-empty lists of names that are all in `repos`. Errors are `LoadError` with the file path in the message.
- Derived file format (spec section 7.6): dataset `repos.touched` in `repos.json`: `{"period": {"since": ..., "until": ...}, "basis": "configuration", "scopes": {"all": {"touched": {"total": n, "list": [{"name": ...}]}}, "group:<name>": {...}}}`. Lists are sorted alphabetically by name; `total` equals the list length; one `group:<name>` scope per configured group.
- The repogrid `footnote` is optional text shown small at the bottom of the scene; textContent only; it must be taken into account when fitting the folder grid.
- Classic scripts: exactly one `export default`, no `import`.
- Run tests with `python3 -m pytest -q` and `node --test tests-js/`; never commit anything under `data/` or `dist/`; do not read or touch `data/` or `.claude/`.
- Commit trailer, as a separate `-m` paragraph: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## File Structure

```
src/team_wrapped/config.py                    # create: Config, load_config
src/team_wrapped/derive.py                    # create: derive_repos, write_repos
src/team_wrapped/cli.py                       # modify: derive-repos command
tests/test_config.py                          # create
tests/test_derive.py                          # create
data-sample/config.yml                        # create: sample config
data-sample/derived/repos.json                # modify: add group:beta
web/scene-types/repogrid/render.js            # modify: footnote
tests-js/repogrid.test.js                     # modify: footnote tests
web/player/player.css                         # modify: footnote style
docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md   # modify
README.md                                     # modify: config and derive-repos
```

---

### Task 1: Config loader and the `derive-repos` command

**Interfaces:**
- Consumes: `LoadError` from `team_wrapped.scenes.loader`; the CLI in `src/team_wrapped/cli.py` (read it first).
- Produces:
  - `Config(org: str, repos: list[str], groups: dict[str, list[str]], since: str | None, until: str | None)` and `load_config(path) -> Config`.
  - `derive_repos(config) -> dict` (the `repos.json` content) and `write_repos(config, data_root) -> Path` (writes `<data_root>/derived/repos.json`, creating folders, returns the path).
  - CLI `derive-repos [--root .] [--data data]`: loads `<root>/<data>/config.yml`, writes `<root>/<data>/derived/repos.json`, prints `wrote <path>: <n> repositories, <g> groups`; a `LoadError` gives exit code 2 with `error: ...` on stderr.

- [ ] **Step 1: Create the branch**

```bash
git checkout -b feature/repos-config
```
Expected: `Switched to a new branch 'feature/repos-config'`

- [ ] **Step 2: Write the failing tests**

`tests/test_config.py`:
```python
import pytest

from team_wrapped.config import load_config
from team_wrapped.scenes.loader import LoadError

GOOD = """
org: sample-org
since: 2026-01-01
until: 2026-12-31
repos: [sample-api, sample-web, sample-docs]
groups:
  alpha: [sample-api, sample-web]
  beta: [sample-docs]
metrics: [commits, pull_requests]
timezone: UTC
"""


def write(tmp_path, text):
    path = tmp_path / "config.yml"
    path.write_text(text)
    return path


def test_loads_a_valid_config(tmp_path):
    config = load_config(write(tmp_path, GOOD))
    assert config.org == "sample-org"
    assert config.repos == ["sample-api", "sample-web", "sample-docs"]
    assert config.groups == {"alpha": ["sample-api", "sample-web"], "beta": ["sample-docs"]}
    assert (config.since, config.until) == ("2026-01-01", "2026-12-31")     # YAML dates become ISO strings


def test_groups_and_dates_are_optional(tmp_path):
    config = load_config(write(tmp_path, "org: o\nrepos: [a]\n"))
    assert config.groups == {} and config.since is None and config.until is None


@pytest.mark.parametrize("text, message", [
    ("repos: [a]\n", "org"),
    ("org: 'bad org!'\nrepos: [a]\n", "org"),
    ("org: o\n", "repos"),
    ("org: o\nrepos: []\n", "repos"),
    ("org: o\nrepos: a\n", "repos"),
    ("org: o\nrepos: [a, a]\n", "duplicate"),
    ("org: o\nrepos: ['a/b']\n", "repository name"),
    ("org: o\nrepos: [a]\ngroups: [x]\n", "groups"),
    ("org: o\nrepos: [a]\ngroups: {g: [b]}\n", "not in repos"),
    ("org: o\nrepos: [a]\ngroups: {g: []}\n", "empty"),
    ("org: o\nrepos: [a]\ngroups: {'bad name': [a]}\n", "group name"),
    ("org: o\nrepos: [a]\nrepoz: [b]\n", "unknown key"),
    ("- just\n- a list\n", "mapping"),
])
def test_invalid_configs_are_rejected(tmp_path, text, message):
    with pytest.raises(LoadError, match=message):
        load_config(write(tmp_path, text))


def test_missing_file_and_bad_yaml(tmp_path):
    with pytest.raises(LoadError, match="not found"):
        load_config(tmp_path / "nope.yml")
    with pytest.raises(LoadError, match="config.yml"):
        load_config(write(tmp_path, "org: [unclosed\n"))
```
`tests/test_derive.py`:
```python
import json
import shutil

import pytest

from team_wrapped.cli import main
from team_wrapped.config import Config, load_config
from team_wrapped.derive import derive_repos, write_repos


def config(repos, groups=None, since=None, until=None):
    return Config(org="sample-org", repos=repos, groups=groups or {}, since=since, until=until)


def test_derive_lists_every_repo_sorted_and_counted():
    out = derive_repos(config(["sample-web", "sample-api", "sample-docs"]))
    assert out["basis"] == "configuration"
    assert list(out["scopes"]) == ["all"]
    touched = out["scopes"]["all"]["touched"]
    assert touched == {"total": 3, "list": [{"name": "sample-api"}, {"name": "sample-docs"}, {"name": "sample-web"}]}


def test_derive_adds_one_scope_per_group():
    out = derive_repos(config(["c", "a", "b"], {"g1": ["c", "a"], "g2": ["b"]}, "2026-01-01", "2026-12-31"))
    assert list(out["scopes"]) == ["all", "group:g1", "group:g2"]
    assert out["scopes"]["group:g1"]["touched"] == {"total": 2, "list": [{"name": "a"}, {"name": "c"}]}
    assert out["scopes"]["group:g2"]["touched"]["total"] == 1
    assert out["period"] == {"since": "2026-01-01", "until": "2026-12-31"}


def test_sample_config_matches_the_sample_derived_file(repo_root, sample_root):
    derived = derive_repos(load_config(sample_root / "config.yml"))
    shipped = json.loads((sample_root / "derived" / "repos.json").read_text())
    assert derived["scopes"] == shipped["scopes"]       # the shipped sample stays consistent with its config


def test_write_repos_creates_the_file(tmp_path):
    path = write_repos(config(["a", "b"]), tmp_path)
    assert path == tmp_path / "derived" / "repos.json"
    assert json.loads(path.read_text())["scopes"]["all"]["touched"]["total"] == 2
    assert path.read_text().endswith("\n")


def test_cli_derive_repos(repo_root, sample_root, tmp_path, capsys):
    data = tmp_path / "data"
    shutil.copytree(sample_root, data)
    (data / "derived" / "repos.json").unlink()
    code = main(["derive-repos", "--root", str(repo_root), "--data", str(data)])
    assert code == 0
    assert "14 repositories, 2 groups" in capsys.readouterr().out
    assert (data / "derived" / "repos.json").is_file()


def test_cli_derive_repos_reports_errors(repo_root, tmp_path, capsys):
    (tmp_path / "data").mkdir()
    code = main(["derive-repos", "--root", str(repo_root), "--data", str(tmp_path / "data")])
    assert code == 2
    assert "not found" in capsys.readouterr().err
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_config.py tests/test_derive.py -q`
Expected: FAIL: `ModuleNotFoundError: No module named 'team_wrapped.config'`.

- [ ] **Step 4: Add the sample config and extend the sample derived file**

`data-sample/config.yml`:
```yaml
# Sample collection config: the same layout as your private data/config.yml.
# `derive-repos` turns it into data/derived/repos.json for the repositories scene.
org: sample-org
since: 2026-01-01
until: 2026-12-31
repos:
  - sample-analytics
  - sample-api
  - sample-auth
  - sample-billing
  - sample-cli
  - sample-design-system
  - sample-docs
  - sample-gateway
  - sample-infra
  - sample-mobile
  - sample-notifications
  - sample-sdk
  - sample-search
  - sample-web
groups:
  alpha:
    - sample-api
    - sample-auth
    - sample-billing
    - sample-docs
    - sample-gateway
    - sample-mobile
    - sample-notifications
    - sample-search
    - sample-web
  beta:
    - sample-analytics
    - sample-cli
    - sample-design-system
    - sample-infra
    - sample-sdk
```
Then read `data-sample/derived/repos.json` (its `all` and `group:alpha` lists are the 14 and the 9 repos in config order). Rewrite the file so that its `scopes` equal exactly what `derive_repos(load_config("data-sample/config.yml"))["scopes"]` produces: lists sorted alphabetically by name, a `group:beta` scope (5 repos) after `group:alpha`; keep `period` and add `"basis": "configuration"`. (Generate it with the new `write_repos` once Step 5 is done and compare; do not hand-edit if the command can write it.) Also update `data-sample/README.md`'s mention of the derived folder to say `repos.json` is produced by `derive-repos` from `config.yml`.

- [ ] **Step 5: Implement the config loader**

`src/team_wrapped/config.py`:
```python
"""Load and validate the private collection config (data/config.yml, spec section 4)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .scenes.loader import LoadError

_KNOWN_KEYS = {
    "org", "repos", "groups", "since", "until", "metrics", "commit_branches", "bot_patterns",
    "aliases", "timezone", "curiosities", "avatars", "reviewer_pairs",
}
_ORG = re.compile(r"[A-Za-z0-9-]+")
_REPO = re.compile(r"[A-Za-z0-9._-]+")
_GROUP = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


@dataclass(frozen=True)
class Config:
    org: str
    repos: list
    groups: dict = field(default_factory=dict)
    since: str | None = None
    until: str | None = None


def _date(value) -> str | None:
    return None if value is None else str(value)


def load_config(path) -> Config:
    path = Path(path)
    if not path.is_file():
        raise LoadError(f"config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as error:
        raise LoadError(f"{path}: invalid YAML ({error})") from error
    if not isinstance(data, dict):
        raise LoadError(f"{path}: must be a mapping")
    unknown = set(data) - _KNOWN_KEYS
    if unknown:
        raise LoadError(f"{path}: unknown key(s) {sorted(unknown)}")

    org = data.get("org")
    if not isinstance(org, str) or not _ORG.fullmatch(org):
        raise LoadError(f"{path}: org must be a GitHub organisation name")

    repos = data.get("repos")
    if not isinstance(repos, list) or not repos:
        raise LoadError(f"{path}: repos must be a non-empty list")
    seen = set()
    for repo in repos:
        if not isinstance(repo, str) or not _REPO.fullmatch(repo):
            raise LoadError(f"{path}: '{repo}' is not a valid repository name")
        if repo in seen:
            raise LoadError(f"{path}: duplicate repository '{repo}'")
        seen.add(repo)

    raw_groups = data.get("groups")
    groups: dict = {}
    if raw_groups is not None:
        if not isinstance(raw_groups, dict):
            raise LoadError(f"{path}: groups must be a mapping of group name to repositories")
        for name, members in raw_groups.items():
            if not isinstance(name, str) or not _GROUP.fullmatch(name):
                raise LoadError(f"{path}: '{name}' is not a valid group name")
            if not isinstance(members, list) or not members:
                raise LoadError(f"{path}: group '{name}' is empty or not a list")
            missing = [m for m in members if m not in seen]
            if missing:
                raise LoadError(f"{path}: group '{name}' has repositories not in repos: {missing}")
            groups[name] = list(members)

    return Config(org=org, repos=list(repos), groups=groups,
                  since=_date(data.get("since")), until=_date(data.get("until")))
```

- [ ] **Step 6: Implement the derivation**

`src/team_wrapped/derive.py`:
```python
"""Derive datasets from the collection config (spec section 7.6)."""
from __future__ import annotations

import json
from pathlib import Path

from .config import Config


def _touched(names) -> dict:
    ordered = sorted(names)
    return {"touched": {"total": len(ordered), "list": [{"name": n} for n in ordered]}}


def derive_repos(config: Config) -> dict:
    """`repos.json` content. Until activity is collected every configured repository counts as touched."""
    scopes = {"all": _touched(config.repos)}
    for name, members in config.groups.items():
        scopes[f"group:{name}"] = _touched(members)
    return {
        "period": {"since": config.since, "until": config.until},
        "basis": "configuration",
        "scopes": scopes,
    }


def write_repos(config: Config, data_root) -> Path:
    path = Path(data_root) / "derived" / "repos.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(derive_repos(config), indent=2) + "\n")
    return path
```

- [ ] **Step 7: Add the CLI command**

In `src/team_wrapped/cli.py` (read it first): import `from .config import load_config` and `from .derive import write_repos`; add a function
```python
def _cmd_derive_repos(args) -> int:
    data_root = Path(args.root) / args.data
    config = load_config(data_root / "config.yml")
    path = write_repos(config, data_root)
    print(f"wrote {path}: {len(config.repos)} repositories, {len(config.groups)} groups")
    return 0
```
register a subparser `derive-repos` with `--root` (default `.`) and `--data` (default `data`), and dispatch to it in `main` before the existing handling, keeping the existing `except LoadError` that prints `error: ...` and returns 2.

- [ ] **Step 8: Regenerate the sample file and run everything**

Run: `PYTHONPATH=src python3 -m team_wrapped derive-repos --data data-sample` (this rewrites `data-sample/derived/repos.json`; check `git diff` shows the sorted lists, `group:beta` and `basis`), then `python3 -m pytest -q`.
Expected: all pass.

- [ ] **Step 9: Spec and README**

In `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`: (a) section 7.6, at the end of the "Repositories touched" bullet add: `Until the aggregator exists, `derive-repos` writes this file from the configured `repos` and `groups` (every configured repository counts as touched) and marks it with `"basis": "configuration"`.`; (b) section 8, in the CLI list add: `- `derive-repos`: write `data/derived/repos.json` from `data/config.yml` (interim, see section 7.6)`; (c) section 4, add a sentence after the options table: `The loader (`config.py`) validates `org`, `repos`, `groups`, `since` and `until` today; the other keys are accepted and validated when the collector uses them.`
In `README.md` add, before the "Themes" section:
```markdown
## Repositories config

Your private `data/config.yml` lists the GitHub organisation, the repositories and optional groups (see `data-sample/config.yml`). `derive-repos` turns it into the dataset the repositories scene needs:

```bash
PYTHONPATH=src python3 -m team_wrapped derive-repos --data data
```

For now every configured repository counts as "touched"; the file is marked `"basis": "configuration"` until activity is collected from GitHub.
```

- [ ] **Step 10: Commit**

```bash
git add src tests data-sample docs README.md
git commit -m "Add the collection config loader and the derive-repos command" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Optional footnote on the repositories scene

**Interfaces:**
- Consumes: `presets.fadeIn`, `presets.fitFolderSize`, the helpers in `tests-js/helpers.js`; the existing `render` helper and constants in `tests-js/repogrid.test.js` (read it first).
- Produces: `repogrid` param `footnote` (optional non-empty string): a `div.tw-repos-footnote` appended after the grid (or after the heading when there are no folders), faded in at 3.4 s (0.6 s); the fit calculation subtracts its height: `availH = wrap.clientHeight - heading.offsetTop - heading.offsetHeight - 24 - (footnote ? footnote.offsetHeight : 0)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests-js/repogrid.test.js` (reuse its `render`, `dataFor`, `PARAMS`, `find`, `presets`):
```js
test("an optional footnote sits at the bottom of the scene and fades in late", () => {
  const { tl, container } = render({ ...PARAMS, footnote: "Some repositories are not included" }, dataFor(NAMES));
  const wrap = container.children[0];
  const last = wrap.children[wrap.children.length - 1];
  assert.strictEqual(last.className, "tw-repos-footnote");
  assert.strictEqual(last.textContent, "Some repositories are not included");
  const fade = tl.calls.find((c) => c.kind === "from" && c.targets === last);
  assert.ok(fade);
  assert.strictEqual(Math.round(fade.at * 100) / 100, 3.4);
});

test("without a footnote, or with an empty one, there is no footnote element", () => {
  assert.strictEqual(find(render(PARAMS, dataFor(NAMES)).container, "tw-repos-footnote").length, 0);
  assert.strictEqual(find(render({ ...PARAMS, footnote: "" }, dataFor(NAMES)).container, "tw-repos-footnote").length, 0);
});

test("the folder fit leaves room for the footnote", () => {
  const names = Array.from({ length: 45 }, (_, i) => `repo-${i}`);
  const sized = (params) => {
    const tl = fakeTimeline();
    const container = makeEl("section");
    loadRenderer("repogrid", { clientWidth: 1500, clientHeight: 682, offsetTop: 24, offsetHeight: 60 })
      .render({ container, data: dataFor(names), params, partial: [], duration: 8, gsap: { timeline: () => tl }, presets });
    return find(container, "tw-folders")[0] || container.children[0].children.find((c) => c.className.startsWith("tw-folders"));
  };
  const without = sized(PARAMS).style["--tw-folder"];
  const withNote = sized({ ...PARAMS, footnote: "note" }).style["--tw-folder"];
  // heading 60 + footnote 60 in the stub: 574 px available without a footnote, 514 with one
  assert.strictEqual(without, presets.fitFolderSize(45, 1120, 574).size + "px");
  assert.strictEqual(withNote, presets.fitFolderSize(45, 1120, 514).size + "px");
  assert.notStrictEqual(without, withNote);
});
```
(In this file `loadRenderer(type, elDefaults)` comes from `tests-js/helpers.js`; if the existing fit test already shows how elDefaults are passed, copy that pattern. The grid element has class `tw-folders tw-folders-<size>`, so locate it by class prefix as above.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tests-js/repogrid.test.js`
Expected: FAIL: no footnote element and the fit ignores it.

- [ ] **Step 3: Implement**

In `web/scene-types/repogrid/render.js` (read it first): after the grid (inside the same `wrap`, after the `if (names.length > 0) { ... }` block that appends the grid, and before `container.append(wrap)`), add:
```js
    // Optional footnote, small at the bottom of the scene.
    let footnote = null;
    if (typeof params.footnote === "string" && params.footnote !== "") {
      footnote = document.createElement("div");
      footnote.className = "tw-repos-footnote";
      footnote.textContent = params.footnote;
      wrap.append(footnote);
      presets.fadeIn(tl, footnote, 3.4, 0.6);
    }
```
and change the fit calculation (the existing line computing `availH`) to subtract the footnote's height: `... - 24 - (footnote ? footnote.offsetHeight : 0)`. Note: the fit runs after `container.append(wrap)`, so make sure the footnote is created and appended before that code and that `footnote` is in scope there (move the footnote block above the fit block if needed).
Append to `web/player/player.css`:
```css
.tw-repos-footnote { margin: 0 0 0.4rem; padding: 0 1rem; font-size: 0.85rem; text-align: center; opacity: 0.7; }
```

- [ ] **Step 4: Spec line**

In `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`, section 13, `Initial types`: change `` `repogrid` (a heading with a highlighted count and a grid of folders)`` to `` `repogrid` (a heading with a highlighted count, a grid of folders and an optional footnote)``.

- [ ] **Step 5: Run everything**

Run: `node --test tests-js/ && python3 -m pytest -q && grep -nE '#[0-9a-fA-F]{3,8}\b' web/player/player.css`
Expected: all pass; the grep lists only the `:root` block.

- [ ] **Step 6: Syntax-check and build**

Run: `cp web/scene-types/repogrid/render.js "$TMPDIR/repogrid.mjs" && node --check "$TMPDIR/repogrid.mjs" && PYTHONPATH=src python3 -m team_wrapped build year-wrapped --data data-sample --out "$TMPDIR/tw-footnote"`
Expected: no syntax errors; `built .../tw-footnote/year-wrapped/index.html`.

- [ ] **Step 7: Commit**

```bash
git add web tests-js docs
git commit -m "Add an optional footnote to the repositories scene" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Not in this plan

- The private importer that reads the org-config, the private config and scene override, and viewing the result: the controller does these by hand in the git-ignored `data/`.
- Real activity collection from GitHub (the collector) and the aggregator: until then every configured repository counts as touched.
