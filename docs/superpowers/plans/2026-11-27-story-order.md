# Story Order and Opening Heading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give scene one the opening line "This year, we worked hard" above the commits number, and reorder the Year Wrapped so it tells a story: effort, the work, the numbers, (curiosities, still to build), extent, people.

**Architecture:** The `bignumber` scene type gets an optional `heading` param (a line above the number; the count-up and supporting figures start a little later so the heading can be read first). Scene `we-shipped` uses it, and `scripts/year-wrapped.yml` is reordered.

**Tech Stack:** classic-script JavaScript renderer tested with `node --test`, GSAP timelines, Python tests for the build output.

Builds on the earlier plans (all on `main`).

## Global Constraints

- Renderers are classic scripts: exactly one `export default { render(ctx) }`, no `import`; data shown with `textContent`, never `innerHTML`; `render(ctx)` returns a GSAP timeline.
- Without a `heading` the `bignumber` timing is unchanged: hero count-up at 0.3 s (2.5 s long), supporting figures from 2.8 s (spec section 13 and the earlier plan).
- With a `heading`, the hero count-up starts at 0.3 + 0.7 = 1.0 s and the supporting figures at 2.8 + 0.7 + i * 0.2 s; the scene still fits its 6 s default duration.
- Scenes stay scope-agnostic; no new dataset; scene ids are unchanged (the script references them).
- Scene order in the script (new): `we-shipped`, `we-looked-after-each-other`, `year-in-numbers` (skip when line data is missing), `repos-touched` (skip for a quiet scope), `we-changed-the-code` (skip when line data is missing), `how-many-of-us`. A comment marks where curiosity scenes will go.
- Run tests with `node --test tests-js/` and `python3 -m pytest -q`; never commit anything under `data/` or `dist/`; do not read or touch `data/` or `.claude/`.
- Commit trailer, as a separate `-m` paragraph: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## File Structure

```
web/scene-types/bignumber/render.js   # modify: optional heading
web/player/player.css                 # modify: heading style
tests-js/bignumber.test.js            # modify: heading tests
scenes/we-shipped.yml                 # modify: heading, title
scripts/year-wrapped.yml              # modify: new order
tests/scenes/test_build.py            # modify: expectations that list the scenes of year-wrapped
docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md   # modify: bignumber description
```

---

### Task 1: Optional heading on `bignumber`, scene one text, new scene order

**Interfaces:**
- Consumes: `presets.countUp`, `presets.popIn`, `presets.fadeIn`, `presets.lookup`, `presets.isPartial`; `tests-js/helpers.js` `{makeEl, loadRenderer, fakeTimeline, find, finishCountUps}`; the existing `render` helper, `DATA` and `PARAMS` in `tests-js/bignumber.test.js`.
- Produces: `bignumber` param `heading` (optional string): a `div.tw-hero-heading` as the first child of `div.tw-hero`, inside the wrapper that already fades in; count-up and supporting timings shift by `+0.7` s when a heading is present.

- [ ] **Step 1: Create the branch**

```bash
git checkout -b feature/story-order
```
Expected: `Switched to a new branch 'feature/story-order'`

- [ ] **Step 2: Write the failing tests**

Append to `tests-js/bignumber.test.js` (reuse the file's existing `render`, `DATA`, `PARAMS`, `find`; read the file first to match its names):
```js
test("an optional heading sits above the number", () => {
  const { container } = render({ ...PARAMS, heading: "This year, we worked hard" }, DATA);
  const wrap = container.children[0];
  assert.strictEqual(wrap.className, "tw-hero");
  assert.deepStrictEqual(wrap.children.slice(0, 3).map((c) => c.className),
    ["tw-hero-heading", "tw-hero-value", "tw-hero-label"]);
  assert.strictEqual(wrap.children[0].textContent, "This year, we worked hard");
});

test("without a heading there is no heading element", () => {
  const { container } = render(PARAMS, DATA);
  assert.strictEqual(find(container, "tw-hero-heading").length, 0);
});

test("a heading delays the count-ups so it can be read first", () => {
  const round2 = (n) => Math.round(n * 100) / 100;
  const counts = (params) => render(params, DATA).tl.calls
    .filter((c) => c.kind === "to" && "v" in c.vars).map((c) => round2(c.at));
  assert.deepStrictEqual(counts(PARAMS), [0.3, 2.8]);                                   // unchanged without a heading
  assert.deepStrictEqual(counts({ ...PARAMS, heading: "H" }), [1.0, 3.5]);             // everything 0.7 s later
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `node --test tests-js/bignumber.test.js`
Expected: FAIL: no `tw-hero-heading` element and the count-up times do not shift.

- [ ] **Step 4: Update the renderer**

In `web/scene-types/bignumber/render.js` (read it first), make these changes and nothing else:
1. Right after `wrap.className = "tw-hero";` add:
```js
    // Optional line above the number. Everything else starts a little later so it can be read first.
    const hasHeading = typeof params.heading === "string" && params.heading !== "";
    if (hasHeading) {
      const heading = document.createElement("div");
      heading.className = "tw-hero-heading";
      heading.textContent = params.heading;
      wrap.append(heading);
    }
    const delay = hasHeading ? 0.7 : 0;
```
2. Change the hero count-up call `presets.countUp(tl, value, hero, 0.3, 2.5);` to `presets.countUp(tl, value, hero, 0.3 + delay, 2.5);`.
3. Change the supporting count-up call `presets.countUp(tl, subValue, raw, 2.8 + i * 0.2, 1.0);` to `presets.countUp(tl, subValue, raw, 2.8 + delay + i * 0.2, 1.0);` and the `presets.popIn(tl, cards, 2.8, 0.2);` call to `presets.popIn(tl, cards, 2.8 + delay, 0.2);`.
The wrapper's own `fadeIn` is unchanged (the heading fades in with the wrapper).

- [ ] **Step 5: Style the heading**

Append to `web/player/player.css`:
```css
.tw-hero-heading { margin-bottom: 1.4rem; font-size: clamp(1.6rem, 5vw, 3rem); font-weight: 700; text-align: center; }
```

- [ ] **Step 6: Scene one and the new order**

Replace the contents of `scenes/we-shipped.yml` with:
```yaml
id: we-shipped
title: We worked hard
type: bignumber
requires:
  - dataset: summary.totals
    fields: [commits]
    allow_partial: false
params:
  heading: "This year, we worked hard"
  value: summary.totals.commits
  label: "Commits"
```
Replace the `scenes:` list of `scripts/year-wrapped.yml` (keep `id`, `title`, `period`, `scope`) with:
```yaml
scenes:
  - scene: we-shipped                  # 1. effort
  - scene: we-looked-after-each-other  # 2. the work
  - scene: year-in-numbers             # 3. the numbers (recap grid)
    on_missing_data: skip   # needs enriched line data; the rest still plays without it
  # 4. curiosities will go here
  - scene: repos-touched               # 5. extent: the repositories...
    on_missing_data: skip   # an empty repo list counts as missing data, so a quiet scope skips the scene
  - scene: we-changed-the-code         # ...and the lines of change
    on_missing_data: skip   # needs enriched line data; the rest still plays without it
  - scene: how-many-of-us              # 6. people: the finale
```
(preserve the existing comment wording on the `on_missing_data` lines if it differs slightly; the point is each of the three scenes keeps `on_missing_data: skip`).

- [ ] **Step 7: Update the tests that list the scenes**

Read `tests/scenes/test_build.py` and `tests/scenes/test_validate.py`. Update every assertion that depends on the order of the `year-wrapped` scenes. Expected new values: payload scene ids in the order `["we-shipped", "we-looked-after-each-other", "year-in-numbers", "repos-touched", "we-changed-the-code", "how-many-of-us"]`; durations `[6.0, 6.0, 8.0, 8.0, 6.0, 10.0]`; when `derived/delivery_volume.json` is deleted, `result.skipped == ["year-in-numbers", "we-changed-the-code"]` and the payload ids `["we-shipped", "we-looked-after-each-other", "repos-touched", "how-many-of-us"]`; `test_validate.py` compares statuses as a dict (order-independent), so only check it still passes. Do not weaken any assertion.

- [ ] **Step 8: Update the spec**

In `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`, section 13, in the `Initial types` line, change `bignumber` (one hero number with optional supporting figures)` so it reads `` `bignumber` (one hero number with an optional heading above it and optional supporting figures)``.

- [ ] **Step 9: Run everything**

Run: `node --test tests-js/ && python3 -m pytest -q && PYTHONPATH=src python3 -m team_wrapped validate-script year-wrapped --data data-sample && grep -nE '#[0-9a-fA-F]{3,8}\b' web/player/player.css`
Expected: all tests pass; validate lists the six scenes in the new order, all supported or partial; the grep lists only the `:root` block.

- [ ] **Step 10: Syntax-check and build**

Run: `cp web/scene-types/bignumber/render.js "$TMPDIR/bignumber.mjs" && node --check "$TMPDIR/bignumber.mjs" && PYTHONPATH=src python3 -m team_wrapped build year-wrapped --data data-sample --out "$TMPDIR/tw-story"`
Expected: no syntax errors; `built .../tw-story/year-wrapped/index.html`.

- [ ] **Step 11: Commit**

```bash
git add web tests-js scenes scripts tests docs
git commit -m "Open with 'This year, we worked hard' and reorder the scenes into a story" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Not in this plan

- The curiosity scenes (and their scene type and data); the script only marks where they go.
- A heading line on the recap grid ("Here's the year in numbers"), which the `stats` scene type does not support yet.
- Playing the wrap in a browser: the controller checks it by hand afterwards.
