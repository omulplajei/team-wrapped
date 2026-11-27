# Dramatic Count-Up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On scene one the number must race up very fast, slow a lot toward the end, and land its last increment really slowly, for a dramatic effect.

**Architecture:** `presets.countUp` gets an optional ease argument (default unchanged). The `bignumber` scene type gets two optional params, `count_duration` and `count_ease`, passed to the hero count-up. Scene `we-shipped` sets `count_ease: expo.out`, `count_duration: 4.5` and a longer scene `duration: 8`.

**Tech Stack:** classic-script JavaScript (presets, renderer) tested with `node --test`, GSAP eases, Python tests for the build output.

Builds on the earlier plans (all on `main`, plus the unmerged branch `feature/story-order` that this work continues on).

## Global Constraints

- Defaults are unchanged: `countUp(tl, el, to, at = 0, duration = 1.2, ease = "power1.out")`; `bignumber` without the new params counts for 2.5 s with `power1.out` (hero) exactly as before; supporting figures keep their own 1.0 s `power1.out` count-up.
- The displayed number is always an integer (`Math.round`), formatted by `presets.format`; the final value is exact.
- Ease names are only ever passed to GSAP, never into the DOM, CSS or HTML.
- Renderers are classic scripts: exactly one `export default`, no `import`; textContent only.
- The scene keeps fitting its duration: heading delay 0.7 s + count start 0.3 s + `count_duration` 4.5 s ends at 5.5 s, inside the scene's 8 s.
- Run tests with `node --test tests-js/` and `python3 -m pytest -q`; never commit anything under `data/` or `dist/`; do not read or touch `data/` or `.claude/`.
- Commit trailer, as a separate `-m` paragraph: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## File Structure

```
web/presets/presets.js              # modify: countUp ease argument
tests-js/presets.test.js            # modify: ease test
web/scene-types/bignumber/render.js # modify: count_duration, count_ease
tests-js/bignumber.test.js          # modify: new tests
scenes/we-shipped.yml               # modify: dramatic count, duration 8
tests/scenes/test_build.py          # modify: duration list
docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md   # modify: bignumber description
```

---

### Task 1: Ease and duration for the count-up, and the dramatic opening

**Interfaces:**
- Consumes: `presets.countUp`, the existing tests and helpers (`tests-js/helpers.js`).
- Produces: `presets.countUp(tl, el, to, at = 0, duration = 1.2, ease = "power1.out")`: the `to` tween's vars carry `ease`. `bignumber` params `count_duration` (number, seconds, default 2.5) and `count_ease` (string, default `"power1.out"`) apply to the hero count-up only. Scene `we-shipped`: `count_ease: "expo.out"`, `count_duration: 4.5`, `duration: 8`.

- [ ] **Step 1: Branch state**

You continue on the existing branch `feature/story-order` (already checked out). Confirm with `git branch --show-current`.
Expected: `feature/story-order`

- [ ] **Step 2: Write the failing tests**

Append to `tests-js/presets.test.js`:
```js
test("countUp takes an optional ease and keeps power1.out by default", () => {
  const calls = [];
  const tl = { to: (target, vars, at) => { calls.push({ vars, at }); return tl; } };
  presets.countUp(tl, { textContent: "" }, 10, 0, 1);
  presets.countUp(tl, { textContent: "" }, 10, 0, 1, "expo.out");
  assert.strictEqual(calls[0].vars.ease, "power1.out");
  assert.strictEqual(calls[1].vars.ease, "expo.out");
});
```
Append to `tests-js/bignumber.test.js` (reuse the file's `render`, `DATA`, `PARAMS`):
```js
test("count_duration and count_ease shape the hero count-up only", () => {
  const counts = (params) => render(params, DATA).tl.calls.filter((c) => c.kind === "to" && "v" in c.vars);
  const dflt = counts(PARAMS);
  assert.strictEqual(dflt[0].vars.duration, 2.5);
  assert.strictEqual(dflt[0].vars.ease, "power1.out");
  const dramatic = counts({ ...PARAMS, count_duration: 4.5, count_ease: "expo.out" });
  assert.strictEqual(dramatic[0].vars.duration, 4.5);
  assert.strictEqual(dramatic[0].vars.ease, "expo.out");
  // the supporting figure keeps its own 1.0 s power1.out count-up
  assert.strictEqual(dramatic[1].vars.duration, 1.0);
  assert.strictEqual(dramatic[1].vars.ease, "power1.out");
});

test("invalid count settings fall back to the defaults", () => {
  const hero = (params) => render(params, DATA).tl.calls.find((c) => c.kind === "to" && "v" in c.vars).vars;
  const bad = hero({ ...PARAMS, count_duration: "slow", count_ease: 5 });
  assert.strictEqual(bad.duration, 2.5);
  assert.strictEqual(bad.ease, "power1.out");
  assert.strictEqual(hero({ ...PARAMS, count_duration: -1 }).duration, 2.5);
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `node --test tests-js/`
Expected: FAIL: `countUp` ignores the ease; the hero count-up ignores `count_duration` and `count_ease`.

- [ ] **Step 4: Add the ease to `countUp`**

In `web/presets/presets.js`, change the signature `function countUp(tl, el, to, at = 0, duration = 1.2) {` to `function countUp(tl, el, to, at = 0, duration = 1.2, ease = "power1.out") {` and, inside it, change the tween's `ease: "power1.out",` to `ease,`.

- [ ] **Step 5: Use the new params in `bignumber`**

In `web/scene-types/bignumber/render.js` (read it first): before the hero count-up add
```js
    // Optional shaping of the hero count-up (for example a dramatic expo.out); invalid values fall back to the defaults.
    const countDuration = typeof params.count_duration === "number" && params.count_duration > 0 ? params.count_duration : 2.5;
    const countEase = typeof params.count_ease === "string" && params.count_ease !== "" ? params.count_ease : "power1.out";
```
and change the hero call `presets.countUp(tl, value, hero, 0.3 + delay, 2.5);` to `presets.countUp(tl, value, hero, 0.3 + delay, countDuration, countEase);`. Leave the supporting count-ups as they are.

- [ ] **Step 6: Scene one and the tests that list durations**

Replace the contents of `scenes/we-shipped.yml` with:
```yaml
id: we-shipped
title: We worked hard
type: bignumber
duration: 8
requires:
  - dataset: summary.totals
    fields: [commits]
    allow_partial: false
params:
  heading: "This year, we worked hard"
  value: summary.totals.commits
  label: "Commits"
  # Race up fast, then slow right down so the last increments land one at a time.
  count_ease: "expo.out"
  count_duration: 4.5
```
In `tests/scenes/test_build.py`, update the expected durations of `year-wrapped` from `[6.0, 6.0, 8.0, 8.0, 6.0, 10.0]` to `[8.0, 6.0, 8.0, 8.0, 6.0, 10.0]` (read the file; change only that list).

- [ ] **Step 7: Spec**

In `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`, section 13, in the `Initial types` line, change `` `bignumber` (one hero number with an optional heading above it and optional supporting figures)`` to `` `bignumber` (one hero number with an optional heading above it, optional supporting figures and an optional count-up duration and ease)``.

- [ ] **Step 8: Run everything**

Run: `node --test tests-js/ && python3 -m pytest -q && PYTHONPATH=src python3 -m team_wrapped validate-script year-wrapped --data data-sample`
Expected: all pass; validate unchanged (six scenes).

- [ ] **Step 9: Syntax-check and build**

Run: `cp web/scene-types/bignumber/render.js "$TMPDIR/bignumber.mjs" && node --check "$TMPDIR/bignumber.mjs" && PYTHONPATH=src python3 -m team_wrapped build year-wrapped --data data-sample --out "$TMPDIR/tw-dramatic"`
Expected: no syntax errors; `built .../tw-dramatic/year-wrapped/index.html`.

- [ ] **Step 10: Commit**

```bash
git add web tests-js scenes tests docs
git commit -m "Make the opening count race up and crawl to the last increment" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Not in this plan

- Checking the feel of the count in a browser: the controller samples the displayed number over time by hand afterwards.
- A different ease for the supporting figures or for other scenes.
