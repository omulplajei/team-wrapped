# Repositories-Touched Scene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a scene, placed third in the Year Wrapped, that shows every repository touched as a folder icon with its name inside. The folders appear like bubbles, settle into a grid with a small bounce, under a heading such as "Across 14 repositories" in which the number is highlighted.

**Architecture:** A new dataset `repos.touched` (count and repo names) is added to the catalog, spec and sample data; the validator learns to check list references; a new `repogrid` scene type renders the heading and folder grid using a new `bubbleIn` animation preset; a scene file and a script change place it third.

**Tech Stack:** Python 3.11+ (pytest), classic-script JavaScript renderers tested with `node --test`, GSAP timelines (already vendored).

Builds on `2026-11-26-scenes-and-player.md` and `2026-11-26-bignumber-scenes.md` (both done and on `main`).

## Global Constraints

- Renderers are classic scripts: exactly one `export default { render(ctx) }`, no `import` lines; the build rewrites `export default` and wraps the file in an IIFE (spec section 13).
- `render(ctx)` receives `{container, data, params, duration, partial, scope, period, gsap, presets}`, returns a GSAP timeline, touches only `container`; data is shown with `textContent` or element properties, never `innerHTML`.
- Shared scenes are scope-agnostic: no repo or group names in `scenes/` or `scripts/` (the sample repo names live only in `data-sample/`).
- A scene may only require datasets listed in `docs/datasets.md`.
- Derived file format: dataset `family.name` resolves to `<family>.json` then `scopes[<scope>][name]` (spec section 7.6). The new dataset is `repos.touched`, in `repos.json`.
- A repository is "touched" when it has at least one commit, pull request, review or comment inside the configured window, among the enabled metrics.
- Run tests with `python3 -m pytest -q` and `node --test tests-js/`; never commit anything under `data/` or `dist/`.
- Commit trailer, as a separate `-m` paragraph: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## File Structure

```
docs/datasets.md                              # modify: add the repos.touched dataset
docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md   # modify: repos.json, definition, names param
data-sample/derived/repos.json                # create
data-sample/derived/meta.json                 # modify: groups cover the new repos
src/team_wrapped/scenes/validate.py           # modify: `names` must resolve to a list
tests/scenes/test_derived.py, test_catalog_and_types.py, test_validate.py   # modify
web/presets/presets.js                        # modify: bubbleIn
tests-js/presets.test.js                      # modify: bubbleIn test
tests-js/helpers.js                           # create: shared renderer-test helpers
tests-js/bignumber.test.js                    # modify: use the shared helpers
tests-js/repogrid.test.js                     # create
web/scene-types/repogrid/type.yml, render.js  # create
web/player/player.css                         # modify: folder and heading styles
scenes/repos-touched.yml                      # create
scripts/year-wrapped.yml                      # modify: scene third
tests/scenes/test_validate.py, test_build.py  # modify: year-wrapped expectations
```

---

### Task 1: The `repos.touched` dataset and list-reference validation

**Files:**
- Modify: `docs/datasets.md`, `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`
- Create: `data-sample/derived/repos.json`
- Modify: `data-sample/derived/meta.json`, `src/team_wrapped/scenes/validate.py`
- Test: `tests/scenes/test_derived.py`, `tests/scenes/test_catalog_and_types.py`, `tests/scenes/test_validate.py`

**Interfaces:**
- Consumes: `DerivedData.dataset(name, scope_key)`, `load_catalog`, `resolve_ref`, the `run`/`make_data`/`TYPES`/`CATALOG`/`REQ` helpers in `tests/scenes/test_validate.py`.
- Produces:
  - dataset `repos.touched` with `total` (int) and `list` (items `{"name": str}`); scopes `all` and `group:alpha` in the sample data (14 and 9 repos).
  - validation rule: a string param named `names` must resolve to a list, otherwise the problem `names '<ref>' does not resolve to a list`.

- [ ] **Step 1: Create the branch**

```bash
git checkout -b feature/repos-scene
```
Expected: `Switched to a new branch 'feature/repos-scene'`

- [ ] **Step 2: Write the failing tests**

In `tests/scenes/test_derived.py`, append:
```python
def test_repos_touched_on_sample(sample_root):
    d = DerivedData(sample_root)
    everything = d.dataset("repos.touched", "all")
    assert everything["total"] == 14
    assert len(everything["list"]) == 14
    assert everything["list"][0] == {"name": "sample-api"}
    alpha = d.dataset("repos.touched", "group:alpha")
    assert alpha["total"] == 9 and len(alpha["list"]) == 9
```

In `tests/scenes/test_catalog_and_types.py`, in `test_catalog_lists_planned_datasets`, add `"repos.touched",` to the list of expected names.

In `tests/scenes/test_validate.py`:
- change `CATALOG = {"summary.totals", "contributors"}` to `CATALOG = {"summary.totals", "contributors", "repos.touched"}`;
- in `TYPES` add `"repogrid": SceneType("repogrid", 8.0, ["heading", "value", "names"], Path(".")),`;
- in `make_data`, after the `summary.json` write, add:
```python
    (d / "repos.json").write_text(json.dumps(
        {"scopes": {"all": {"touched": {"total": 2, "list": [{"name": "a"}, {"name": "b"}]}}}}))
```
- append these tests:
```python
REPO_REQ = [{"dataset": "repos.touched", "fields": ["total", "list.name"]}]


def test_repogrid_names_must_resolve_to_a_list(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "c").mkdir()
    ok = {"heading": "Across {count}", "value": "repos.touched.total", "names": "repos.touched.list"}
    assert run(tmp_path / "a", REPO_REQ, params=ok, type_="repogrid").results[0].status == "supported"
    not_a_list = dict(ok, names="repos.touched.total")
    report = run(tmp_path / "b", REPO_REQ, params=not_a_list, type_="repogrid")
    assert "names 'repos.touched.total' does not resolve to a list" in report.results[0].problems
    missing = dict(ok, names="repos.touched.nope")
    report = run(tmp_path / "c", REPO_REQ, params=missing, type_="repogrid")
    assert "names 'repos.touched.nope' does not resolve to a list" in report.results[0].problems
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m pytest tests/scenes -q`
Expected: FAIL: `repos.json` missing in the sample data, `repos.touched` missing from the catalog, and the `names` check absent.

- [ ] **Step 4: Add the dataset to the catalog**

In `docs/datasets.md`, insert this section directly after the `contributors` section (before `## delivery_volume`):
```markdown
## repos
Metric: any. Not time-bucketed. A repository is "touched" when it has at least one commit, pull request, review or comment inside the configured window, among the enabled metrics.

| Dataset | Fields |
|---|---|
| `repos.touched` | `total`; `list[].name` |
```

- [ ] **Step 5: Add the sample data**

`data-sample/derived/repos.json`:
```json
{
  "period": {"since": "2026-01-01", "until": "2026-12-31"},
  "scopes": {
    "all": {
      "touched": {
        "total": 14,
        "list": [
          {"name": "sample-api"},
          {"name": "sample-web"},
          {"name": "sample-docs"},
          {"name": "sample-auth"},
          {"name": "sample-billing"},
          {"name": "sample-search"},
          {"name": "sample-notifications"},
          {"name": "sample-gateway"},
          {"name": "sample-mobile"},
          {"name": "sample-analytics"},
          {"name": "sample-infra"},
          {"name": "sample-cli"},
          {"name": "sample-sdk"},
          {"name": "sample-design-system"}
        ]
      }
    },
    "group:alpha": {
      "touched": {
        "total": 9,
        "list": [
          {"name": "sample-api"},
          {"name": "sample-web"},
          {"name": "sample-docs"},
          {"name": "sample-auth"},
          {"name": "sample-billing"},
          {"name": "sample-search"},
          {"name": "sample-notifications"},
          {"name": "sample-gateway"},
          {"name": "sample-mobile"}
        ]
      }
    }
  }
}
```
In `data-sample/derived/meta.json`, replace the `"groups"` value with:
```json
"groups": {
    "alpha": ["sample-api", "sample-web", "sample-docs", "sample-auth", "sample-billing", "sample-search", "sample-notifications", "sample-gateway", "sample-mobile"],
    "beta": ["sample-analytics", "sample-infra", "sample-cli", "sample-sdk", "sample-design-system"]
  }
```
(keep the rest of `meta.json` as it is and the file valid JSON). In `data-sample/README.md`, in the "Contents so far" list, change the `derived/` line so it also names `repos.json`.

- [ ] **Step 6: Implement the list check**

In `src/team_wrapped/scenes/validate.py`, directly after the `for ref in _value_refs(...)` loop inside `validate_script`, add:
```python
        names_ref = scene.params.get("names")
        if isinstance(names_ref, str) and not isinstance(resolve_ref(datasets, names_ref), list):
            problems.append(f"names '{names_ref}' does not resolve to a list")
```

- [ ] **Step 7: Update the spec**

In `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`:
1. Section 7.6, the **Files.** bullet: add `repos.json` to the list of files (after `contributors.json`).
2. Section 7.6, after the **Curiosities.** bullet, add a bullet:
```
- **Repositories touched.** `repos.json` holds `touched` with `total` and `list` (items `{"name": ...}`) per scope. A repository is touched when it has at least one commit, pull request, review or comment inside the window, among the enabled metrics.
```
3. Section 13, in the **Scene types** subsection, append to the bullet that starts with `- `type.yml`:` the sentence:
```
A param named `names` is a data reference that must resolve to a list.
```

- [ ] **Step 8: Run the full Python suite**

Run: `python3 -m pytest -q`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add docs data-sample src tests
git commit -m "Add the repos.touched dataset and list-reference validation" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The `bubbleIn` preset and the `repogrid` scene type

**Files:**
- Modify: `web/presets/presets.js`, `tests-js/presets.test.js`, `tests-js/bignumber.test.js`, `web/player/player.css`
- Create: `tests-js/helpers.js`, `tests-js/repogrid.test.js`, `web/scene-types/repogrid/type.yml`, `web/scene-types/repogrid/render.js`

**Interfaces:**
- Consumes: `presets.lookup`, `presets.fadeIn`, `presets.countUp` (existing).
- Produces:
  - `presets.bubbleIn(tl, targets, at = 0, each = 0.08, duration = 1.1)`: GSAP `from` tween; each target starts small, transparent, below and sideways of its grid position (deterministic offsets from the target index) and settles with an elastic bounce; returns `tl`.
  - scene type `repogrid`: params `heading` (string with a `{count}` placeholder, required), `heading_one` (optional singular heading), `value` (reference to the count, required), `names` (reference to a list of `{name}` objects or strings, required); default duration 8 s.
  - DOM classes: `tw-repos`, `tw-repos-heading`, `tw-repos-text`, `tw-repos-count`, `tw-folders` (plus `tw-folders-lg`, `tw-folders-md` or `tw-folders-sm`: at most 12 repos, at most 30, more), `tw-folder`, `tw-folder-body`, `tw-folder-name`.
  - `tests-js/helpers.js` exports `{makeEl, loadRenderer, fakeTimeline, find, finishCountUps}`.

- [ ] **Step 1: Extract the shared test helpers**

Create `tests-js/helpers.js` with the helper code that is currently at the top of `tests-js/bignumber.test.js` (the minimal DOM stub, the renderer loader, the fake timeline, `find` and `finishCountUps`):
```js
const fs = require("node:fs");
const path = require("node:path");

// A minimal DOM: just enough for the renderers, which only build elements.
function makeEl(tag) {
  const el = { tag, className: "", textContent: "", children: [] };
  el.append = (...kids) => { el.children.push(...kids); };
  el.appendChild = (kid) => { el.children.push(kid); return kid; };
  return el;
}

// Load render.js the way the build does: `export default` becomes an assignment.
function loadRenderer(type) {
  const file = path.join(__dirname, "..", "web", "scene-types", type, "render.js");
  const source = fs.readFileSync(file, "utf8").replace("export default", "module.exports =");
  const module = { exports: {} };
  new Function("module", "document", source)(module, { createElement: makeEl });
  return module.exports;
}

function fakeTimeline() {
  const calls = [];
  const tl = {
    calls,
    from: (targets, vars, at) => { calls.push({ kind: "from", targets, vars, at }); return tl; },
    to: (target, vars, at) => { calls.push({ kind: "to", target, vars, at }); return tl; },
  };
  return tl;
}

function find(el, className, found = []) {
  if (el.className === className) found.push(el);
  (el.children || []).forEach((kid) => find(kid, className, found));
  return found;
}

// Run every count-up to its end so the elements show their final text.
function finishCountUps(tl) {
  tl.calls.filter((c) => c.kind === "to").forEach((c) => { c.target.v = c.vars.v; c.vars.onUpdate(); });
}

module.exports = { makeEl, loadRenderer, fakeTimeline, find, finishCountUps };
```
Then edit `tests-js/bignumber.test.js`: delete the now-duplicated definitions of `makeEl`, `loadRenderer`, `fakeTimeline`, `find` and `finishCountUps` (and the `fs`/`path` requires if nothing else uses them), and import them instead:
```js
const { makeEl, loadRenderer, fakeTimeline, find, finishCountUps } = require("./helpers.js");
```
Keep the tests and the local `render` helper unchanged.

- [ ] **Step 2: Verify the refactor kept the existing tests green**

Run: `node --test tests-js/`
Expected: 15 pass, 0 fail.

- [ ] **Step 3: Write the failing tests**

Append to `tests-js/presets.test.js`:
```js
test("bubbleIn adds one staggered from-tween with deterministic offsets and returns the timeline", () => {
  const calls = [];
  const tl = { from: (t, v, at) => { calls.push({ t, v, at }); return tl; } };
  assert.strictEqual(presets.bubbleIn(tl, [{}, {}, {}], 0.6, 0.1), tl);
  assert.strictEqual(calls.length, 1);
  const { v, at } = calls[0];
  assert.strictEqual(at, 0.6);
  assert.strictEqual(v.stagger, 0.1);
  assert.strictEqual(v.opacity, 0);
  assert.ok(v.scale > 0 && v.scale < 1);
  assert.ok(/^elastic/.test(v.ease));
  // offsets are functions of the target index, so scrubbing and replaying never changes the layout
  assert.strictEqual(typeof v.y, "function");
  assert.strictEqual(typeof v.x, "function");
  assert.strictEqual(v.y(3), v.y(3));
  assert.ok(v.y(0) > 0);                     // bubbles rise from below
  assert.notStrictEqual(v.x(1), v.x(2));     // and come from different sides
});
```

Create `tests-js/repogrid.test.js`:
```js
const test = require("node:test");
const assert = require("node:assert");
const presets = require("../web/presets/presets.js");
const { makeEl, loadRenderer, fakeTimeline, find, finishCountUps } = require("./helpers.js");

const NAMES = ["alpha-api", "beta-web", "gamma-docs"];
const dataFor = (names) => ({
  "repos.touched": { total: names.length, list: names.map((name) => ({ name })) },
});
const PARAMS = {
  heading: "Across {count} repositories",
  heading_one: "Across {count} repository",
  value: "repos.touched.total",
  names: "repos.touched.list",
};

function render(params, data) {
  const tl = fakeTimeline();
  const container = makeEl("section");
  const result = loadRenderer("repogrid").render({
    container, data, params, partial: [], duration: 8, gsap: { timeline: () => tl }, presets,
  });
  return { tl, container, result };
}

test("the heading wraps the highlighted count in its own element", () => {
  const { tl, container, result } = render(PARAMS, dataFor(NAMES));
  assert.strictEqual(result, tl);
  finishCountUps(tl);
  const texts = find(container, "tw-repos-text").map((e) => e.textContent);
  assert.deepStrictEqual(texts, ["Across ", " repositories"]);
  assert.strictEqual(find(container, "tw-repos-count")[0].textContent, "3");
});

test("a single repository uses the singular heading", () => {
  const { tl, container } = render(PARAMS, dataFor(["only-one"]));
  finishCountUps(tl);
  const texts = find(container, "tw-repos-text").map((e) => e.textContent);
  assert.deepStrictEqual(texts, ["Across ", " repository"]);
  assert.strictEqual(find(container, "tw-repos-count")[0].textContent, "1");
});

test("there is one folder per repository with its name inside", () => {
  const { container } = render(PARAMS, dataFor(NAMES));
  const folders = find(container, "tw-folder");
  assert.strictEqual(folders.length, 3);
  assert.deepStrictEqual(find(container, "tw-folder-name").map((e) => e.textContent), NAMES);
  assert.deepStrictEqual(folders.map((f) => f.title), NAMES);
});

test("the folder size class follows the number of repositories", () => {
  const many = (n) => Array.from({ length: n }, (_, i) => `repo-${i}`);
  assert.strictEqual(render(PARAMS, dataFor(many(3))).container.children[0].children[1].className, "tw-folders tw-folders-lg");
  assert.strictEqual(render(PARAMS, dataFor(many(20))).container.children[0].children[1].className, "tw-folders tw-folders-md");
  assert.strictEqual(render(PARAMS, dataFor(many(40))).container.children[0].children[1].className, "tw-folders tw-folders-sm");
});

test("the folders bubble in with a stagger that keeps the whole entrance short", () => {
  const small = render(PARAMS, dataFor(NAMES)).tl.calls.filter((c) => c.kind === "from");
  const bubble = small.find((c) => Array.isArray(c.targets) && c.targets.length === 3);
  assert.ok(bubble);
  assert.strictEqual(bubble.vars.stagger, 0.12);
  const names = Array.from({ length: 50 }, (_, i) => `repo-${i}`);
  const big = render(PARAMS, dataFor(names)).tl.calls.filter((c) => c.kind === "from");
  const crowd = big.find((c) => Array.isArray(c.targets) && c.targets.length === 50);
  assert.ok(crowd.vars.stagger * 50 <= 2.5 + 1e-9);
});

test("no repositories shows the heading with 0 and no grid", () => {
  const { tl, container } = render(PARAMS, dataFor([]));
  finishCountUps(tl);
  assert.strictEqual(find(container, "tw-repos-count")[0].textContent, "0");
  assert.strictEqual(find(container, "tw-folders").length, 0);
});

test("a missing count shows a dash", () => {
  const { container } = render(PARAMS, {});
  assert.strictEqual(find(container, "tw-repos-count")[0].textContent, "–");
});
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `node --test tests-js/`
Expected: FAIL: `presets.bubbleIn is not a function`, and `ENOENT` for `web/scene-types/repogrid/render.js`.

- [ ] **Step 5: Add the `bubbleIn` preset**

In `web/presets/presets.js`, add this function after `popIn` and add `bubbleIn` to the exported `api` object:
```js
  // Bubbles rise from below and from varied sides, then settle in place with a small bounce.
  // Offsets depend only on the target index, so scrubbing and replaying look identical.
  function bubbleIn(tl, targets, at = 0, each = 0.08, duration = 1.1) {
    return tl.from(targets, {
      opacity: 0,
      scale: 0.2,
      y: (i) => 160 + ((i * 53) % 90),
      x: (i) => ((i * 37) % 120) - 60,
      duration,
      stagger: each,
      ease: "elastic.out(1, 0.6)",
    }, at);
  }
```
The `api` line becomes: `const api = { format, lookup, isPartial, fadeIn, stagger, popIn, bubbleIn, countUp };`

- [ ] **Step 6: Create the scene type**

`web/scene-types/repogrid/type.yml`:
```yaml
name: repogrid
default_duration: 8
required_params: [heading, value, names]
```

`web/scene-types/repogrid/render.js`:
```js
export default {
  render(ctx) {
    const { container, data, params, gsap, presets } = ctx;
    const tl = gsap.timeline();

    const total = presets.lookup(data, params.value);
    const rows = presets.lookup(data, params.names);
    const names = (Array.isArray(rows) ? rows : []).map((row) => (typeof row === "string" ? row : row.name));

    const wrap = document.createElement("div");
    wrap.className = "tw-repos";

    // Heading: "Across <count> repositories", with the count in its own element so it can be highlighted.
    const template = total === 1 && params.heading_one ? params.heading_one : params.heading;
    const marker = "{count}";
    const at = template.indexOf(marker);
    const textSpan = (value) => {
      const span = document.createElement("span");
      span.className = "tw-repos-text";
      span.textContent = value;
      return span;
    };
    const heading = document.createElement("div");
    heading.className = "tw-repos-heading";
    const count = document.createElement("span");
    count.className = "tw-repos-count";
    heading.append(textSpan(at < 0 ? template : template.slice(0, at)));
    if (at >= 0) {
      heading.append(count);
      heading.append(textSpan(template.slice(at + marker.length)));
    }
    if (typeof total === "number") {
      presets.countUp(tl, count, total, 0.4, 2.0);
    } else {
      count.textContent = "–";
    }
    wrap.append(heading);
    presets.fadeIn(tl, heading, 0, 0.6);

    // Folders: one per repository, bubbling in and settling into the grid.
    if (names.length > 0) {
      const sizeClass = names.length <= 12 ? "lg" : names.length <= 30 ? "md" : "sm";
      const grid = document.createElement("div");
      grid.className = "tw-folders tw-folders-" + sizeClass;
      const folders = names.map((name) => {
        const folder = document.createElement("div");
        folder.className = "tw-folder";
        folder.title = name;
        const body = document.createElement("div");
        body.className = "tw-folder-body";
        const label = document.createElement("span");
        label.className = "tw-folder-name";
        label.textContent = name;
        body.append(label);
        folder.append(body);
        grid.append(folder);
        return folder;
      });
      wrap.append(grid);
      // Cap the stagger so large teams do not overrun the scene.
      presets.bubbleIn(tl, folders, 0.6, Math.min(0.12, 2.5 / folders.length));
    }

    container.append(wrap);
    return tl;
  },
};
```

- [ ] **Step 7: Add the styles**

Append to `web/player/player.css`:
```css
.tw-repos { width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; }
.tw-repos-heading { margin-top: 1.5rem; font-size: clamp(1.6rem, 5vw, 3rem); font-weight: 700; text-align: center; }
.tw-repos-count { color: #5eead4; font-weight: 800; font-variant-numeric: tabular-nums; }

.tw-folders { --tw-folder: 8rem; --tw-folder-font: 0.8rem; margin: auto 0; display: grid;
  grid-template-columns: repeat(auto-fit, var(--tw-folder)); justify-content: center;
  gap: 1.6rem 1.2rem; width: min(70rem, 100%); }
.tw-folders-md { --tw-folder: 6rem; --tw-folder-font: 0.65rem; gap: 1.3rem 1rem; }
.tw-folders-sm { --tw-folder: 4.6rem; --tw-folder-font: 0.52rem; gap: 1rem 0.7rem; }

.tw-folder { position: relative; width: var(--tw-folder); height: calc(var(--tw-folder) * 0.75); }
.tw-folder::before { content: ""; position: absolute; top: -0.45em; left: 0; width: 42%; height: 0.6em;
  background: #d99a2b; border-radius: 6px 6px 0 0; }
.tw-folder-body { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  padding: 0.3rem; background: linear-gradient(#f4c75f, #e0a93b); border-radius: 0 8px 8px 8px;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.35); color: #2a1f05; font-weight: 600;
  font-size: var(--tw-folder-font); line-height: 1.15; text-align: center; overflow: hidden; overflow-wrap: anywhere; }
```

- [ ] **Step 8: Run the tests**

Run: `node --test tests-js/ && python3 -m pytest -q`
Expected: JS: 23 pass, 0 fail (9 timing/presets plus 1 new preset test, 6 bignumber, 7 repogrid). Python: all pass.

- [ ] **Step 9: Check the build's syntax rule on the new renderer**

Run: `cp web/scene-types/repogrid/render.js "$TMPDIR/repogrid.mjs" && node --check "$TMPDIR/repogrid.mjs" && echo ok`
Expected: `ok`

- [ ] **Step 10: Commit**

```bash
git add web tests-js
git commit -m "Add bubbleIn preset and the repogrid scene type" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The scene and its place in the script

**Files:**
- Create: `scenes/repos-touched.yml`
- Modify: `scripts/year-wrapped.yml`
- Modify: `tests/scenes/test_validate.py` (`test_year_wrapped_on_sample`), `tests/scenes/test_build.py` (`test_build_year_wrapped_on_sample` and any other test that depends on the scene list)

**Interfaces:**
- Consumes: `repogrid` (Task 2), `repos.touched` and the `names` validation (Task 1).
- Produces: scene `repos-touched`; the script plays: `we-shipped`, `we-looked-after-each-other`, `repos-touched`, `we-changed-the-code`, `year-in-numbers`, `how-many-of-us`.

- [ ] **Step 1: Update the two sample-script tests (they fail first)**

In `tests/scenes/test_validate.py`, in `test_year_wrapped_on_sample`, replace the `assert statuses == {...}` with:
```python
    assert statuses == {
        "we-shipped": "supported",
        "we-looked-after-each-other": "supported",
        "repos-touched": "supported",
        "we-changed-the-code": "partial",
        "year-in-numbers": "partial",
        "how-many-of-us": "supported",
    }
```
and add `assert "repos-touched: supported" in text` next to the other `format_report` text assertions.

In `tests/scenes/test_build.py`, in `test_build_year_wrapped_on_sample`: change the expected id list to
```python
    assert [s["id"] for s in payload["scenes"]] == [
        "we-shipped", "we-looked-after-each-other", "repos-touched",
        "we-changed-the-code", "year-in-numbers", "how-many-of-us",
    ]
```
the durations list to `[6.0, 6.0, 8.0, 6.0, 8.0, 10.0]`, add `assert scenes["repos-touched"]["partial"] == []` and `assert scenes["repos-touched"]["data"]["repos.touched"]["total"] == 14` next to the other per-scene assertions, and add `assert 'TeamWrapped.sceneTypes["repogrid"]' in html` next to the other `sceneTypes` assertions. In `test_build_skips_scenes_marked_skip`-style and the delivery_volume-missing test, the expected payload ids after skipping `we-changed-the-code` and `year-in-numbers` become `["we-shipped", "we-looked-after-each-other", "repos-touched", "how-many-of-us"]` (update that assertion). Read the whole file first and adjust any other assertion that lists the scenes of `year-wrapped`.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/scenes/test_validate.py tests/scenes/test_build.py -q`
Expected: the updated tests FAIL because the scene does not exist yet.

- [ ] **Step 3: Create the scene file**

`scenes/repos-touched.yml`:
```yaml
id: repos-touched
title: Repositories touched
type: repogrid
requires:
  - dataset: repos.touched
    fields: [total, list.name]
    allow_partial: false
params:
  heading: "Across {count} repositories"
  heading_one: "Across {count} repository"
  value: repos.touched.total
  names: repos.touched.list
```

- [ ] **Step 4: Put it third in the script**

In `scripts/year-wrapped.yml`, add the entry `  - scene: repos-touched` directly after the `we-looked-after-each-other` entry (so it is the third scene), leaving the rest as it is.

- [ ] **Step 5: Run everything**

Run: `python3 -m pytest -q && node --test tests-js/ && PYTHONPATH=src python3 -m team_wrapped validate-script year-wrapped --data data-sample`
Expected: all tests pass; the validate output is
```
year-wrapped
  we-shipped: supported
  we-looked-after-each-other: supported
  repos-touched: supported
  we-changed-the-code: partial
  year-in-numbers: partial
  how-many-of-us: supported
```

- [ ] **Step 6: Build once into a temp folder**

Run: `PYTHONPATH=src python3 -m team_wrapped build year-wrapped --data data-sample --out "$TMPDIR/tw-repos"`
Expected: `built .../tw-repos/year-wrapped/index.html`; then `node --check "$TMPDIR/tw-repos/year-wrapped/assets/player.js"` passes.

- [ ] **Step 7: Commit**

```bash
git add scenes scripts tests
git commit -m "Add the repositories-touched scene as the third scene" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Not in this plan

- The aggregator that produces `repos.json` from real data (plan 2); this plan only defines the dataset and provides sample data.
- Playing the scene in a browser: the controller checks the bubble motion, the grid and the highlighted count by hand afterwards.
- Click or hover behaviour on folders, folder icons from an image or SVG file, and per-repo statistics inside the folder.
