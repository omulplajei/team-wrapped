# Big-Number Scenes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the "year in numbers" opening into three high-impact scenes (one hero number each, with supporting figures) using a new `bignumber` scene type, and keep the existing stats grid as the recap.

**Architecture:** A new scene type folder `web/scene-types/bignumber/` (`type.yml` + `render.js`) built on the existing presets; the validator learns to check the new scene type's value references; three new scene files and an updated `year-wrapped` script wire it together. No new datasets.

**Tech Stack:** Python 3.11+ (pytest), JavaScript classic-script renderers tested with `node --test`, GSAP timelines (already vendored).

Builds on `docs/superpowers/plans/2026-11-26-scenes-and-player.md` (all tasks done and merged to `main`).

## Global Constraints

- Renderers are classic scripts: exactly one `export default { render(ctx) }`, no `import` lines; the build rewrites `export default` and wraps the file in an IIFE (spec section 13).
- `render(ctx)` receives `{container, data, params, duration, partial, scope, period, gsap, presets}` and returns a GSAP timeline; it touches only `container`; data is shown with `textContent`, never `innerHTML`.
- Shared scenes are scope-agnostic: no repo or group names (spec section 12).
- A scene may only require datasets listed in `docs/datasets.md`; no new datasets in this plan.
- Run tests with `python3 -m pytest -q` and `node --test tests-js/`; never commit anything under `data/` or `dist/`.
- Humans in the headcount scene are `human` plus `unlinked`; unchanged by this plan.
- Commit trailer, as a separate `-m` paragraph: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## File Structure

```
src/team_wrapped/scenes/validate.py        # modify: value-reference check for bignumber, numbers only
tests/scenes/test_validate.py              # modify: new tests, bignumber in TYPES
web/scene-types/bignumber/type.yml         # create
web/scene-types/bignumber/render.js        # create
web/player/player.css                      # modify: hero styles
tests-js/bignumber.test.js                 # create
scenes/we-shipped.yml                      # create
scenes/we-looked-after-each-other.yml      # create
scenes/we-changed-the-code.yml             # create
scripts/year-wrapped.yml                   # modify: new scene order
tests/scenes/test_validate.py, test_build.py   # modify: year-wrapped expectations
docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md   # modify: list the new type
```

---

### Task 1: Validate numeric value references for `bignumber`

**Files:**
- Modify: `src/team_wrapped/scenes/validate.py` (the value-reference loop in `validate_script`)
- Test: `tests/scenes/test_validate.py`

**Interfaces:**
- Consumes: `resolve_ref(datasets, ref)` from `derived.py`; the existing `run(...)` helper, `TYPES`, `CATALOG`, `REQ` in `tests/scenes/test_validate.py`.
- Produces: `validate_script` now checks every value reference found in `params.value`, `params.items[].value` and `params.supporting[].value`. A reference that does not resolve gives the problem `value '<ref>' does not resolve to required data` (unchanged text); a reference that resolves to something that is not a number (not int/float, or a bool) gives `value '<ref>' is not a number`. Both make the scene `unsupported`.

- [ ] **Step 1: Create a working branch**

```bash
git checkout -b feature/bignumber-scenes
```
Expected: `Switched to a new branch 'feature/bignumber-scenes'`

- [ ] **Step 2: Write the failing tests**

In `tests/scenes/test_validate.py`, change the `TYPES` line to:
```python
TYPES = {
    "stats": SceneType("stats", 8.0, ["items"], Path(".")),
    "bignumber": SceneType("bignumber", 6.0, ["value", "label"], Path(".")),
}
```
and append these tests at the end of the file:
```python
def test_bignumber_refs_resolve(tmp_path):
    params = {"value": "summary.totals.commits", "label": "Commits",
              "supporting": [{"label": "Same", "value": "summary.totals.commits"}]}
    report = run(tmp_path, REQ, params=params, type_="bignumber")
    assert report.results[0].status == "supported"


def test_bignumber_unresolved_hero_and_supporting(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    bad_hero = {"value": "summary.totals.nope", "label": "X"}
    report = run(tmp_path / "a", REQ, params=bad_hero, type_="bignumber")
    assert "value 'summary.totals.nope' does not resolve to required data" in report.results[0].problems
    bad_sub = {"value": "summary.totals.commits", "label": "X",
               "supporting": [{"label": "Y", "value": "summary.totals.nope"}]}
    report = run(tmp_path / "b", REQ, params=bad_sub, type_="bignumber")
    assert "value 'summary.totals.nope' does not resolve to required data" in report.results[0].problems


def test_value_must_be_a_number(tmp_path):
    params = {"items": [{"label": "C", "value": "summary.totals"}]}   # a whole dataset, not a number
    report = run(tmp_path, REQ, params=params)
    assert "value 'summary.totals' is not a number" in report.results[0].problems
    assert report.results[0].status == "unsupported"


def test_bignumber_requires_value_and_label(tmp_path):
    report = run(tmp_path, REQ, params={"value": "summary.totals.commits"}, type_="bignumber")
    assert "missing required param 'label'" in report.results[0].problems
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m pytest tests/scenes/test_validate.py -q`
Expected: FAIL. `test_bignumber_refs_resolve` passes vacuously or fails on the unknown behaviour; `test_bignumber_unresolved_hero_and_supporting` and `test_value_must_be_a_number` fail because only `params.items` is checked and non-numbers are accepted.

- [ ] **Step 4: Implement the check**

In `src/team_wrapped/scenes/validate.py`, add this helper above `validate_script`:
```python
def _value_refs(params: dict) -> list[str]:
    """Every data reference a scene's params carry: value, items[].value, supporting[].value."""
    refs = []
    if isinstance(params.get("value"), str):
        refs.append(params["value"])
    for key in ("items", "supporting"):
        entries = params.get(key)
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and isinstance(entry.get("value"), str):
                    refs.append(entry["value"])
    return refs
```
and replace the existing loop
```python
        for item in scene.params.get("items", []):
            ref = item.get("value") if isinstance(item, dict) else None
            if ref is not None and resolve_ref(datasets, ref) is None:
                problems.append(f"value '{ref}' does not resolve to required data")
```
with:
```python
        for ref in _value_refs(scene.params):
            value = resolve_ref(datasets, ref)
            if value is None:
                problems.append(f"value '{ref}' does not resolve to required data")
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                problems.append(f"value '{ref}' is not a number")
```

- [ ] **Step 5: Run the full Python suite**

Run: `python3 -m pytest -q`
Expected: all pass (the sample scenes `year-in-numbers` only reference numbers, so they stay supported).

- [ ] **Step 6: Commit**

```bash
git add src/team_wrapped/scenes/validate.py tests/scenes/test_validate.py
git commit -m "Validate numeric value references for bignumber scenes" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The `bignumber` scene type

**Files:**
- Create: `web/scene-types/bignumber/type.yml`, `web/scene-types/bignumber/render.js`
- Modify: `web/player/player.css`
- Test: `tests-js/bignumber.test.js`

**Interfaces:**
- Consumes: `presets.lookup`, `presets.isPartial`, `presets.fadeIn`, `presets.popIn`, `presets.countUp` (all in `web/presets/presets.js`); the `ctx` object described in Global Constraints.
- Produces: scene type `bignumber` with params `value` (data reference, required), `label` (string, required), `supporting` (optional list of `{label, value}`); default duration 6 s. DOM classes: `tw-hero`, `tw-hero-value`, `tw-hero-label`, `tw-hero-partial`, `tw-hero-supporting`, `tw-hero-sub`, `tw-hero-sub-value`, `tw-hero-sub-label`, `tw-hero-sub-partial`.

- [ ] **Step 1: Write the failing tests**

`tests-js/bignumber.test.js`:
```js
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const presets = require("../web/presets/presets.js");

// A minimal DOM: just enough for the renderer, which only builds elements.
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

function render(params, data, partial = []) {
  const tl = fakeTimeline();
  const container = makeEl("section");
  const result = loadRenderer("bignumber").render({
    container, data, params, partial, duration: 6, gsap: { timeline: () => tl }, presets,
  });
  return { tl, container, result };
}

// Run every count-up to its end so the elements show their final text.
function finishCountUps(tl) {
  tl.calls.filter((c) => c.kind === "to").forEach((c) => { c.target.v = c.vars.v; c.vars.onUpdate(); });
}

const DATA = { "summary.totals": { commits: 1240, merged_prs: 310 } };
const PARAMS = {
  value: "summary.totals.commits",
  label: "Commits",
  supporting: [{ label: "Merged pull requests", value: "summary.totals.merged_prs" }],
};

test("hero counts up to the value and shows its label", () => {
  const { tl, container, result } = render(PARAMS, DATA);
  assert.strictEqual(result, tl);
  finishCountUps(tl);
  assert.strictEqual(find(container, "tw-hero-value")[0].textContent, "1,240");
  assert.strictEqual(find(container, "tw-hero-label")[0].textContent, "Commits");
});

test("supporting figures show their label and value", () => {
  const { tl, container } = render(PARAMS, DATA);
  finishCountUps(tl);
  assert.strictEqual(find(container, "tw-hero-sub-value")[0].textContent, "310");
  assert.strictEqual(find(container, "tw-hero-sub-label")[0].textContent, "Merged pull requests");
});

test("the hero count-up runs longer than the supporting one", () => {
  const { tl } = render(PARAMS, DATA);
  const durations = tl.calls.filter((c) => c.kind === "to").map((c) => c.vars.duration);
  assert.deepStrictEqual(durations, [2.5, 1.0]);
});

test("no supporting row without a supporting param", () => {
  const { container } = render({ value: "summary.totals.commits", label: "Commits" }, DATA);
  assert.strictEqual(find(container, "tw-hero-supporting").length, 0);
});

test("a missing hero value shows a dash and is not animated", () => {
  const { tl, container } = render({ value: "summary.totals.nope", label: "X" }, DATA);
  assert.strictEqual(find(container, "tw-hero-value")[0].textContent, "–");
  assert.strictEqual(tl.calls.filter((c) => c.kind === "to").length, 0);
});

test("partial datasets are labelled on the hero and on supporting figures", () => {
  const { container } = render(PARAMS, DATA, ["summary.totals"]);
  assert.strictEqual(find(container, "tw-hero-partial").length, 1);
  assert.strictEqual(find(container, "tw-hero-sub-partial").length, 1);
  const none = render(PARAMS, DATA, []);
  assert.strictEqual(find(none.container, "tw-hero-partial").length, 0);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tests-js/bignumber.test.js`
Expected: FAIL with `ENOENT` for `web/scene-types/bignumber/render.js`

- [ ] **Step 3: Write the scene type**

`web/scene-types/bignumber/type.yml`:
```yaml
name: bignumber
default_duration: 6
required_params: [value, label]
```

`web/scene-types/bignumber/render.js`:
```js
export default {
  render(ctx) {
    const { container, data, params, partial, gsap, presets } = ctx;
    const tl = gsap.timeline();

    const wrap = document.createElement("div");
    wrap.className = "tw-hero";
    const value = document.createElement("div");
    value.className = "tw-hero-value";
    const label = document.createElement("div");
    label.className = "tw-hero-label";
    label.textContent = params.label;
    wrap.append(value, label);

    const hero = presets.lookup(data, params.value);
    if (typeof hero === "number") {
      presets.countUp(tl, value, hero, 0.3, 2.5);
    } else {
      value.textContent = "–";
    }
    if (presets.isPartial(partial, params.value)) {
      const badge = document.createElement("div");
      badge.className = "tw-hero-partial";
      badge.textContent = "partial data";
      wrap.append(badge);
    }

    const supporting = Array.isArray(params.supporting) ? params.supporting : [];
    if (supporting.length > 0) {
      const row = document.createElement("div");
      row.className = "tw-hero-supporting";
      const cards = [];
      supporting.forEach((item, i) => {
        const card = document.createElement("div");
        card.className = "tw-hero-sub";
        const subValue = document.createElement("div");
        subValue.className = "tw-hero-sub-value";
        const subLabel = document.createElement("div");
        subLabel.className = "tw-hero-sub-label";
        subLabel.textContent = item.label;
        card.append(subValue, subLabel);

        const raw = presets.lookup(data, item.value);
        if (typeof raw === "number") {
          presets.countUp(tl, subValue, raw, 2.8 + i * 0.2, 1.0);
        } else {
          subValue.textContent = "–";
        }
        if (presets.isPartial(partial, item.value)) {
          const subBadge = document.createElement("div");
          subBadge.className = "tw-hero-sub-partial";
          subBadge.textContent = "partial data";
          card.append(subBadge);
        }
        row.append(card);
        cards.push(card);
      });
      wrap.append(row);
      presets.popIn(tl, cards, 2.8, 0.2);
    }

    container.append(wrap);
    presets.fadeIn(tl, wrap, 0, 0.6);
    return tl;
  },
};
```

- [ ] **Step 4: Add the styles**

Append to `web/player/player.css`:
```css
.tw-hero { text-align: center; }
.tw-hero-value { font-size: clamp(4rem, 16vw, 11rem); font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }
.tw-hero-label { font-size: clamp(1.2rem, 3vw, 2rem); opacity: 0.8; margin-top: 0.6rem; }
.tw-hero-partial { margin-top: 0.4rem; font-size: 0.8rem; color: #e6b450; }
.tw-hero-supporting { display: flex; justify-content: center; flex-wrap: wrap; gap: 2.5rem; margin-top: 2.5rem; }
.tw-hero-sub-value { font-size: clamp(1.6rem, 5vw, 2.6rem); font-weight: 700; font-variant-numeric: tabular-nums; }
.tw-hero-sub-label { opacity: 0.75; font-size: 0.95rem; }
.tw-hero-sub-partial { margin-top: 0.2rem; font-size: 0.7rem; color: #e6b450; }
```

- [ ] **Step 5: Run the tests**

Run: `node --test tests-js/ && python3 -m pytest -q`
Expected: JS: 15 pass, 0 fail (9 existing plus 6 new). Python: all pass (the type is loaded by `load_scene_types`; the existing catalog-and-types test only asserts the three older types are present).

- [ ] **Step 6: Commit**

```bash
git add web tests-js
git commit -m "Add bignumber scene type" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The three hero scenes and the updated script

**Files:**
- Create: `scenes/we-shipped.yml`, `scenes/we-looked-after-each-other.yml`, `scenes/we-changed-the-code.yml`
- Modify: `scripts/year-wrapped.yml`
- Modify: `tests/scenes/test_validate.py` (`test_year_wrapped_on_sample`), `tests/scenes/test_build.py` (`test_build_year_wrapped_on_sample`)
- Modify: `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`

**Interfaces:**
- Consumes: the `bignumber` type (Task 2) and validation (Task 1); the sample data in `data-sample/derived/` (commits 1240, merged_prs 310, reviews 540, comments 1180; lines total_additions 48200, total_deletions 21350, total_net 26850; `delivery_volume.lines` is partial).
- Produces: scenes `we-shipped`, `we-looked-after-each-other`, `we-changed-the-code`; the script `year-wrapped` now plays: `we-shipped`, `we-looked-after-each-other`, `we-changed-the-code`, `year-in-numbers`, `how-many-of-us`.

- [ ] **Step 1: Update the two sample-script tests (they fail first)**

In `tests/scenes/test_validate.py`, in `test_year_wrapped_on_sample`, replace the `assert statuses == {...}` line with:
```python
    assert statuses == {
        "we-shipped": "supported",
        "we-looked-after-each-other": "supported",
        "we-changed-the-code": "partial",
        "year-in-numbers": "partial",
        "how-many-of-us": "supported",
    }
```
Keep the other assertions of that test.

In `tests/scenes/test_build.py`, in `test_build_year_wrapped_on_sample`, replace the block from `payload = read_payload(result.index)` up to (not including) `html = result.index.read_text()` with:
```python
    payload = read_payload(result.index)
    scenes = {s["id"]: s for s in payload["scenes"]}
    assert [s["id"] for s in payload["scenes"]] == [
        "we-shipped", "we-looked-after-each-other", "we-changed-the-code",
        "year-in-numbers", "how-many-of-us",
    ]
    assert [s["duration"] for s in payload["scenes"]] == [6.0, 6.0, 6.0, 8.0, 10.0]
    assert scenes["we-shipped"]["partial"] == []
    assert scenes["we-changed-the-code"]["partial"] == ["delivery_volume.lines"]
    assert scenes["year-in-numbers"]["partial"] == ["delivery_volume.lines"]
    assert scenes["how-many-of-us"]["partial"] == []
    assert scenes["we-shipped"]["data"]["summary.totals"]["commits"] == 1240
    assert payload["script"]["music"] is None
```
and in the assertions after `html = result.index.read_text()`, add one line next to the existing `sceneTypes` assertions:
```python
    assert 'TeamWrapped.sceneTypes["bignumber"]' in html
```
(keep the existing `stats` and `headcount` assertions and the "message not inlined" assertion).

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/scenes/test_validate.py tests/scenes/test_build.py -q`
Expected: the two tests FAIL because the new scenes do not exist yet.

- [ ] **Step 3: Create the scene files**

`scenes/we-shipped.yml`:
```yaml
id: we-shipped
title: We shipped
type: bignumber
requires:
  - dataset: summary.totals
    fields: [commits, merged_prs]
    allow_partial: false
params:
  value: summary.totals.commits
  label: "Commits"
  supporting:
    - {label: "Merged pull requests", value: summary.totals.merged_prs}
```

`scenes/we-looked-after-each-other.yml`:
```yaml
id: we-looked-after-each-other
title: We looked after each other
type: bignumber
requires:
  - dataset: summary.totals
    fields: [reviews, comments]
    allow_partial: false
params:
  value: summary.totals.reviews
  label: "Reviews"
  supporting:
    - {label: "Comments", value: summary.totals.comments}
```

`scenes/we-changed-the-code.yml`:
```yaml
id: we-changed-the-code
title: We changed the code
type: bignumber
requires:
  - dataset: delivery_volume.lines
    fields: [total_additions, total_deletions, total_net]
    allow_partial: true   # needs enriched commit records
params:
  value: delivery_volume.lines.total_net
  label: "Net lines of change"
  supporting:
    - {label: "Lines added", value: delivery_volume.lines.total_additions}
    - {label: "Lines deleted", value: delivery_volume.lines.total_deletions}
```

- [ ] **Step 4: Update the script**

Replace the contents of `scripts/year-wrapped.yml` with:
```yaml
id: year-wrapped
title: Year Wrapped
period: 2026
scope: all            # all, or a group name
scenes:
  - scene: we-shipped
  - scene: we-looked-after-each-other
  - scene: we-changed-the-code
    on_missing_data: skip   # needs enriched commit data; the rest still plays without it
  - scene: year-in-numbers  # the recap grid of all numbers
  # scenes in between are still to be explored
  - scene: how-many-of-us
```

- [ ] **Step 5: Note the new type in the spec**

In `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`, section 13, find the line `Initial types: `message`, `stats`, `headcount`, `curiosity`, and a media type for images and short video.` and replace it with:
```
Initial types: `message`, `stats`, `bignumber` (one hero number with optional supporting figures), `headcount`, `curiosity`, and a media type for images and short video.
```

- [ ] **Step 6: Run everything**

Run: `python3 -m pytest -q && node --test tests-js/ && PYTHONPATH=src python3 -m team_wrapped validate-script year-wrapped --data data-sample`
Expected: all tests pass; the validate output is
```
year-wrapped
  we-shipped: supported
  we-looked-after-each-other: supported
  we-changed-the-code: partial
  year-in-numbers: partial
  how-many-of-us: supported
```

- [ ] **Step 7: Build once into a temp folder**

Run: `PYTHONPATH=src python3 -m team_wrapped build year-wrapped --data data-sample --out "$TMPDIR/tw-bignumber"`
Expected: `built .../tw-bignumber/year-wrapped/index.html`, then `node --check` on `.../assets/player.js` passes.

- [ ] **Step 8: Commit**

```bash
git add scenes scripts tests docs
git commit -m "Split the year in numbers into three hero scenes plus the recap" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Not in this plan

- Derived context lines and fun comparisons (decided: numbers only for now; a `note` param can be added later).
- Playing the new scenes in a browser: the controller checks this by hand after the tasks are done, as in plan 1.
- The middle of the Year Wrapped (busiest day, review outcomes, curiosities) and the `curiosity` scene type.
