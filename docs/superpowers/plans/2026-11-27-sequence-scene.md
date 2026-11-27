# Sequence Scene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework scene two ("We look after each other") into: a heading at the top, then in the middle the review count popped in directly (no count-up) labelled "Pull requests", the text "and left", and the comment count popped in directly.

**Architecture:** A new `sequence` scene type renders a heading plus an ordered list of steps (a number with a label, or a plain text), each popping in one after another. The scene file `we-looked-after-each-other` switches to this type; the validator learns that `steps[].value` are data references.

**Tech Stack:** Python 3.11+ (pytest), classic-script JavaScript renderer tested with `node --test`, GSAP timelines (already vendored).

Builds on the earlier plans (all on `main`).

## Global Constraints

- Renderers are classic scripts: exactly one `export default { render(ctx) }`, no `import` lines; the build rewrites `export default` and wraps the file in an IIFE (spec section 13).
- `render(ctx)` receives `{container, data, params, duration, partial, scope, period, gsap, presets}`, returns a GSAP timeline, touches only `container`; data shown with `textContent` or element properties, never `innerHTML`.
- Shared scenes are scope-agnostic: no repo or group names.
- A scene may only require datasets listed in `docs/datasets.md`; this plan adds no dataset.
- A value reference in `params.items[].value`, `params.supporting[].value` or (new) `params.steps[].value` must resolve to a number from the scene's required data (spec section 13).
- The scene id `we-looked-after-each-other` stays (the script references it).
- Run tests with `python3 -m pytest -q` and `node --test tests-js/`; never commit anything under `data/` or `dist/`.
- Commit trailer, as a separate `-m` paragraph: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## File Structure

```
src/team_wrapped/scenes/validate.py        # modify: also check steps[].value
tests/scenes/test_validate.py              # modify: new tests, sequence in TYPES
tests/scenes/test_build.py                 # modify: sequence is inlined
web/scene-types/sequence/type.yml          # create
web/scene-types/sequence/render.js         # create
web/player/player.css                      # modify: sequence styles
tests-js/sequence.test.js                  # create
scenes/we-looked-after-each-other.yml      # modify: use the sequence type
docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md   # modify: list the type and steps
```

---

### Task 1: The `sequence` scene type and the reworked scene two

**Files:** as listed above.

**Interfaces:**
- Consumes: `presets.lookup`, `presets.isPartial`, `presets.format`, `presets.fadeIn`, `presets.popIn(tl, targets, at, each, duration)` (all in `web/presets/presets.js`); `tests-js/helpers.js` exports `{makeEl, loadRenderer, fakeTimeline, find, finishCountUps}`; the `run`/`make_data`/`TYPES`/`CATALOG`/`REQ` helpers in `tests/scenes/test_validate.py`.
- Produces: scene type `sequence` with params `heading` (string, required) and `steps` (list, required) whose entries are either `{value: <data reference>, label: <string>}` (a number step) or `{text: <string>}` (a text step); default duration 6 s. DOM classes: `tw-seq`, `tw-seq-heading`, `tw-seq-body`, `tw-seq-step`, `tw-seq-value`, `tw-seq-label`, `tw-seq-partial`, `tw-seq-text`. Validation rule: every string `value` inside `params.steps[]` is checked like `items[].value`.

- [ ] **Step 1: Create the branch**

```bash
git checkout -b feature/sequence-scene
```
Expected: `Switched to a new branch 'feature/sequence-scene'`

- [ ] **Step 2: Write the failing tests**

In `tests/scenes/test_validate.py`:
- add to `TYPES`: `"sequence": SceneType("sequence", 6.0, ["heading", "steps"], Path(".")),`
- append:
```python
def test_sequence_steps_values_are_checked(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "c").mkdir()
    ok = {"heading": "H", "steps": [
        {"value": "summary.totals.commits", "label": "Commits"},
        {"text": "and left"},
        {"value": "summary.totals.commits", "label": "Again"},
    ]}
    assert run(tmp_path / "a", REQ, params=ok, type_="sequence").results[0].status == "supported"
    bad = {"heading": "H", "steps": [{"value": "summary.totals.nope", "label": "X"}]}
    report = run(tmp_path / "b", REQ, params=bad, type_="sequence")
    assert "value 'summary.totals.nope' does not resolve to required data" in report.results[0].problems
    not_a_number = {"heading": "H", "steps": [{"value": "summary.totals", "label": "X"}]}
    report = run(tmp_path / "c", REQ, params=not_a_number, type_="sequence")
    assert "value 'summary.totals' is not a number" in report.results[0].problems
```

`tests-js/sequence.test.js`:
```js
const test = require("node:test");
const assert = require("node:assert");
const presets = require("../web/presets/presets.js");
const { makeEl, loadRenderer, fakeTimeline, find } = require("./helpers.js");

const DATA = { "summary.totals": { reviews: 540, comments: 1180 } };
const PARAMS = {
  heading: "We look after each other",
  steps: [
    { value: "summary.totals.reviews", label: "Pull requests" },
    { text: "and left" },
    { value: "summary.totals.comments", label: "Comments" },
  ],
};

function render(params, data, partial = []) {
  const tl = fakeTimeline();
  const container = makeEl("section");
  const result = loadRenderer("sequence").render({
    container, data, params, partial, duration: 6, gsap: { timeline: () => tl }, presets,
  });
  return { tl, container, result };
}

test("the heading is the first thing in the scene", () => {
  const { tl, container, result } = render(PARAMS, DATA);
  assert.strictEqual(result, tl);
  const wrap = container.children[0];
  assert.strictEqual(wrap.children[0].className, "tw-seq-heading");
  assert.strictEqual(wrap.children[0].textContent, "We look after each other");
});

test("steps appear in order: number, text, number", () => {
  const { container } = render(PARAMS, DATA);
  const body = find(container, "tw-seq-body")[0];
  assert.deepStrictEqual(body.children.map((s) => s.className), ["tw-seq-step", "tw-seq-text", "tw-seq-step"]);
  assert.strictEqual(body.children[1].textContent, "and left");
});

test("numbers show their final value immediately, without a count-up", () => {
  const { tl, container } = render(PARAMS, DATA);
  assert.deepStrictEqual(find(container, "tw-seq-value").map((e) => e.textContent), ["540", "1,180"]);
  assert.deepStrictEqual(find(container, "tw-seq-label").map((e) => e.textContent), ["Pull requests", "Comments"]);
  assert.strictEqual(tl.calls.filter((c) => c.kind === "to").length, 0);   // nothing counts up
});

test("each step pops in on its own, one after another", () => {
  const { tl } = render(PARAMS, DATA);
  const pops = tl.calls.filter((c) => c.kind === "from" && Array.isArray(c.targets) && c.targets.length === 1);
  assert.strictEqual(pops.length, 3);
  const times = pops.map((c) => c.at);
  assert.deepStrictEqual(times, [...times].sort((a, b) => a - b));
  assert.ok(times[0] < times[1] && times[1] < times[2]);
  assert.ok(pops.every((c) => c.vars.scale < 1 && c.vars.opacity === 0));
});

test("a missing value shows a dash", () => {
  const { container } = render(PARAMS, {});
  assert.deepStrictEqual(find(container, "tw-seq-value").map((e) => e.textContent), ["–", "–"]);
});

test("partial datasets are labelled on the number steps", () => {
  const { container } = render(PARAMS, DATA, ["summary.totals"]);
  assert.strictEqual(find(container, "tw-seq-partial").length, 2);
  assert.strictEqual(find(render(PARAMS, DATA, []).container, "tw-seq-partial").length, 0);
});
```

In `tests/scenes/test_build.py`, in `test_build_year_wrapped_on_sample`, add `assert 'TeamWrapped.sceneTypes["sequence"]' in html` next to the other `sceneTypes` assertions.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m pytest tests/scenes -q; node --test tests-js/`
Expected: FAIL: the `steps` references are not validated yet; `ENOENT` for `web/scene-types/sequence/render.js`; the build test fails because `sequence` is not inlined.

- [ ] **Step 4: Validate `steps`**

In `src/team_wrapped/scenes/validate.py`, in `_value_refs`, change `for key in ("items", "supporting"):` to `for key in ("items", "supporting", "steps"):`. (A step with only `text` has no string `value`, so it is skipped.)

- [ ] **Step 5: Create the scene type**

`web/scene-types/sequence/type.yml`:
```yaml
name: sequence
default_duration: 6
required_params: [heading, steps]
```

`web/scene-types/sequence/render.js`:
```js
export default {
  render(ctx) {
    const { container, data, params, partial, gsap, presets } = ctx;
    const tl = gsap.timeline();

    const wrap = document.createElement("div");
    wrap.className = "tw-seq";

    const heading = document.createElement("div");
    heading.className = "tw-seq-heading";
    heading.textContent = params.heading;
    wrap.append(heading);
    presets.fadeIn(tl, heading, 0, 0.6);

    const body = document.createElement("div");
    body.className = "tw-seq-body";
    const steps = Array.isArray(params.steps) ? params.steps : [];

    steps.forEach((step, i) => {
      let el;
      if (typeof step.text === "string") {
        el = document.createElement("div");
        el.className = "tw-seq-text";
        el.textContent = step.text;
      } else {
        el = document.createElement("div");
        el.className = "tw-seq-step";
        const value = document.createElement("div");
        value.className = "tw-seq-value";
        const raw = presets.lookup(data, step.value);
        // Shown at its final value straight away: the pop is the only animation.
        value.textContent = typeof raw === "number" ? presets.format(raw) : "–";
        const label = document.createElement("div");
        label.className = "tw-seq-label";
        label.textContent = step.label;
        el.append(value, label);
        if (presets.isPartial(partial, step.value)) {
          const badge = document.createElement("div");
          badge.className = "tw-seq-partial";
          badge.textContent = "partial data";
          el.append(badge);
        }
      }
      body.append(el);
      presets.popIn(tl, [el], 0.8 + i * 1.0, 0, 0.5);
    });

    wrap.append(body);
    container.append(wrap);
    return tl;
  },
};
```

- [ ] **Step 6: Add the styles**

Append to `web/player/player.css`:
```css
.tw-seq { width: 100%; height: 100%; position: relative; display: flex; flex-direction: column; align-items: center; }
.tw-seq-heading { margin-top: 1.5rem; font-size: clamp(1.6rem, 5vw, 3rem); font-weight: 700; text-align: center; }
.tw-seq-body { margin: auto 0; display: flex; flex-direction: column; align-items: center; gap: 1.6rem; text-align: center; }
.tw-seq-value { font-size: clamp(3.5rem, 13vw, 8rem); font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }
.tw-seq-label { font-size: clamp(1.1rem, 3vw, 1.8rem); opacity: 0.8; margin-top: 0.4rem; }
.tw-seq-partial { margin-top: 0.3rem; font-size: 0.75rem; color: #e6b450; }
.tw-seq-text { font-size: clamp(1.4rem, 4vw, 2.4rem); font-weight: 600; opacity: 0.9; }
```

- [ ] **Step 7: Rework scene two**

Replace the contents of `scenes/we-looked-after-each-other.yml` with:
```yaml
id: we-looked-after-each-other
title: We look after each other
type: sequence
requires:
  - dataset: summary.totals
    fields: [reviews, comments]
    allow_partial: false
params:
  heading: "We look after each other"
  steps:
    - {value: summary.totals.reviews, label: "Pull requests"}
    - {text: "and left"}
    - {value: summary.totals.comments, label: "Comments"}
```

- [ ] **Step 8: Update the spec**

In `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`, section 13:
1. In the `Initial types` line, add `sequence` (a heading and a list of steps, each a number with a label or a plain text, popping in one by one) after `bignumber ...`.
2. In the `type.yml` bullet, change the sentence that starts `Params named `items` and `supporting` carry` so it reads `Params named `items`, `supporting` and `steps` carry `{label, value}` pairs (a `steps` entry may instead be `{text}`) whose `value` is a data reference, ...` (keep the rest of the sentence).

- [ ] **Step 9: Run everything**

Run: `python3 -m pytest -q && node --test tests-js/ && PYTHONPATH=src python3 -m team_wrapped validate-script year-wrapped --data data-sample`
Expected: all tests pass; validate output unchanged (six scenes, `we-looked-after-each-other: supported`).

- [ ] **Step 10: Syntax-check the renderer and build once**

Run: `cp web/scene-types/sequence/render.js "$TMPDIR/sequence.mjs" && node --check "$TMPDIR/sequence.mjs" && PYTHONPATH=src python3 -m team_wrapped build year-wrapped --data data-sample --out "$TMPDIR/tw-seq"`
Expected: no syntax errors; `built .../tw-seq/year-wrapped/index.html`.

- [ ] **Step 11: Commit**

```bash
git add src tests tests-js web scenes docs
git commit -m "Add the sequence scene type and rework scene two" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Not in this plan

- Playing the scene in a browser: the controller checks the pop timing and layout by hand afterwards.
- Renaming the scene id, or changing the label of the comments number (kept as "Comments").
