# Count-Up Tail Beats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On scene one the last few increments of the number must land one at a time with growing pauses, the final one a full second after the one before it, whatever the total is.

**Architecture:** `presets.countUp` gets an optional `tail` list of pauses (seconds). The count runs fast (with the chosen ease) to `total - tail.length`, then each of the last increments is a separate beat after its pause. `bignumber` passes a `count_tail` param to the hero count-up. Scene `we-shipped` sets it.

**Tech Stack:** classic-script JavaScript (presets, renderer) tested with `node --test`, GSAP timelines, Python tests for the build output.

Builds on `2026-11-27-dramatic-count.md` (committed on the branch `feature/story-order`, not yet merged), which this work continues on.

## Global Constraints

- Defaults unchanged: `countUp(tl, el, to, at = 0, duration = 1.2, ease = "power1.out", tail = [])` with no tail makes exactly the same single tween as before (`v: to`).
- The displayed number is always an integer (`Math.round`), formatted by `presets.format`; after the last beat it shows the exact total.
- `tail` entries must be finite numbers greater than 0; anything else is ignored. The number of beats is capped at the (rounded) total so the main count never goes below 0.
- Each beat is an instantaneous step (a 0.05 s tween with ease `none`) of exactly +1, so the displayed number changes by one per beat.
- Beat `i` (1-based) happens at `at + duration + tail[0] + ... + tail[i-1]`.
- Renderers are classic scripts: exactly one `export default`, no `import`; textContent only. Supporting figures keep their own 1.0 s `power1.out` count-up with no tail.
- The scene fits: with heading delay 0.7 s, count start 1.0 s, main count 3.0 s and tail `[0.25, 0.35, 0.5, 0.7, 1.0]` (sum 2.8 s) the last beat is at 6.8 s; the scene duration becomes 9 s.
- Run tests with `node --test tests-js/` and `python3 -m pytest -q`; never commit anything under `data/` or `dist/`; do not read or touch `data/` or `.claude/`.
- Commit trailer, as a separate `-m` paragraph: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## File Structure

```
web/presets/presets.js              # modify: countUp tail beats
tests-js/presets.test.js            # modify: tail tests
web/scene-types/bignumber/render.js # modify: count_tail
tests-js/bignumber.test.js          # modify: tail tests
scenes/we-shipped.yml               # modify: count_tail, count_duration 3.0, duration 9
tests/scenes/test_build.py          # modify: duration list
docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md   # modify: bignumber description
```

---

### Task 1: Tail beats for the count-up

**Interfaces:**
- Consumes: `presets.countUp` (with the ease argument added by the previous plan), `presets.format`, the helpers in `tests-js/helpers.js`.
- Produces: `presets.countUp(tl, el, to, at = 0, duration = 1.2, ease = "power1.out", tail = [])`. `bignumber` param `count_tail` (list of positive numbers, default none), applied to the hero count-up only.

- [ ] **Step 1: Branch state**

You continue on the existing branch `feature/story-order` (already checked out). Confirm with `git branch --show-current`.
Expected: `feature/story-order`

- [ ] **Step 2: Write the failing tests**

Append to `tests-js/presets.test.js`:
```js
function countCalls(to, at, duration, tail) {
  const calls = [];
  const state = { text: "" };
  const el = { textContent: "" };
  const tl = { to: (target, vars, when) => { calls.push({ target, vars, at: when }); return tl; } };
  presets.countUp(tl, el, to, at, duration, "expo.out", tail);
  const run = () => calls.forEach((c) => { c.target.v = c.vars.v; c.vars.onUpdate(); });
  return { calls, el, run };
}
const r2 = (n) => Math.round(n * 100) / 100;

test("without a tail countUp makes one tween to the total, as before", () => {
  const { calls } = countCalls(10, 1, 2, undefined);
  assert.strictEqual(calls.length, 1);
  assert.strictEqual(calls[0].vars.v, 10);
  assert.strictEqual(calls[0].vars.ease, "expo.out");
});

test("a tail counts fast to total minus the beats, then adds one per beat after each pause", () => {
  const { calls, el, run } = countCalls(10, 1, 3, [0.25, 0.5, 1.0]);
  assert.deepStrictEqual(calls.map((c) => c.vars.v), [7, 8, 9, 10]);
  assert.strictEqual(calls[0].vars.duration, 3);
  assert.strictEqual(calls[0].at, 1);
  assert.deepStrictEqual(calls.slice(1).map((c) => r2(c.at)), [4.25, 4.75, 5.75]);      // 1 + 3, then + the pauses
  assert.ok(calls.slice(1).every((c) => c.vars.duration <= 0.05 && c.vars.ease === "none"));
  run();
  assert.strictEqual(el.textContent, "10");                                              // exact total at the end
});

test("invalid tail entries are ignored and the beats never exceed the total", () => {
  const { calls } = countCalls(10, 0, 1, [0, -1, "x", NaN, Infinity, 0.5]);
  assert.deepStrictEqual(calls.map((c) => c.vars.v), [9, 10]);                           // only 0.5 is valid
  const small = countCalls(2, 0, 1, [1, 1, 1]);
  assert.deepStrictEqual(small.calls.map((c) => c.vars.v), [0, 1, 2]);                  // capped at the total
  assert.deepStrictEqual(countCalls(10, 0, 1, "slow").calls.map((c) => c.vars.v), [10]);
});
```
Append to `tests-js/bignumber.test.js` (reuse the file's `render`, `DATA`, `PARAMS`; `round2` is defined locally in other tests, so define a local one in these tests):
```js
test("count_tail makes the last increments land as separate beats after the main count", () => {
  const round2 = (n) => Math.round(n * 100) / 100;
  const params = { ...PARAMS, heading: "H", count_duration: 3.0, count_ease: "expo.out", count_tail: [0.25, 0.35, 0.5, 0.7, 1.0] };
  const hero = render(params, DATA).tl.calls.filter((c) => c.kind === "to" && "v" in c.vars);
  // DATA has 1,240 commits: the main count stops 5 short, then five +1 beats
  const heroCalls = hero.filter((c) => [1235, 1236, 1237, 1238, 1239, 1240].includes(c.vars.v));
  assert.deepStrictEqual(heroCalls.map((c) => c.vars.v), [1235, 1236, 1237, 1238, 1239, 1240]);
  assert.strictEqual(round2(heroCalls[0].at), 1.0);                                      // heading delay 0.7 + 0.3
  assert.deepStrictEqual(heroCalls.slice(1).map((c) => round2(c.at)), [4.25, 4.6, 5.1, 5.8, 6.8]);
});

test("no count_tail, or an invalid one, keeps a single hero tween", () => {
  const heroTweens = (params) => render(params, DATA).tl.calls
    .filter((c) => c.kind === "to" && "v" in c.vars && c.vars.v >= 1200);
  assert.strictEqual(heroTweens(PARAMS).length, 1);
  assert.strictEqual(heroTweens({ ...PARAMS, count_tail: "slow" }).length, 1);
  assert.strictEqual(heroTweens({ ...PARAMS, count_tail: [] }).length, 1);
});

test("supporting figures never get tail beats", () => {
  const sub = render({ ...PARAMS, count_tail: [0.2, 0.3] }, DATA).tl.calls
    .filter((c) => c.kind === "to" && "v" in c.vars && c.vars.v <= 400);                 // merged_prs 310
  assert.strictEqual(sub.length, 1);
  assert.strictEqual(sub[0].vars.v, 310);
});
```
Note on the bignumber tests: `PARAMS` in that file has `supporting` with `summary.totals.merged_prs` (310) and `DATA` has `commits: 1240`; read the file first and adapt the numbers in the assertions if its `DATA` differs, keeping the meaning (hero total minus 5 up to the total; supporting unaffected).

- [ ] **Step 3: Run the tests to verify they fail**

Run: `node --test tests-js/`
Expected: FAIL: `countUp` makes one tween and ignores the tail; `bignumber` ignores `count_tail`.

- [ ] **Step 4: Implement tail beats in `countUp`**

In `web/presets/presets.js`, replace the whole `countUp` function with:
```js
  function countUp(tl, el, to, at = 0, duration = 1.2, ease = "power1.out", tail = []) {
    const state = { v: 0 };
    el.textContent = format(0);
    const show = () => { el.textContent = format(Math.round(state.v)); };
    // Tail beats: the last few increments land one at a time, each after its own pause.
    const pauses = (Array.isArray(tail) ? tail : [])
      .filter((p) => typeof p === "number" && Number.isFinite(p) && p > 0)
      .slice(0, Math.max(0, Math.round(to)));
    const main = to - pauses.length;
    tl.to(state, { v: main, duration, ease, onUpdate: show }, at);
    let when = at + duration;
    pauses.forEach((pause, i) => {
      when += pause;
      tl.to(state, { v: main + i + 1, duration: 0.05, ease: "none", onUpdate: show }, when);
    });
    return tl;
  }
```

- [ ] **Step 5: Use `count_tail` in `bignumber`**

In `web/scene-types/bignumber/render.js` (read it first): next to the `countDuration` and `countEase` lines add
```js
    const countTail = Array.isArray(params.count_tail) ? params.count_tail : [];
```
and change the hero call `presets.countUp(tl, value, hero, 0.3 + delay, countDuration, countEase);` to `presets.countUp(tl, value, hero, 0.3 + delay, countDuration, countEase, countTail);`. Leave the supporting count-ups unchanged.

- [ ] **Step 6: Scene one and the duration list**

Replace the contents of `scenes/we-shipped.yml` with:
```yaml
id: we-shipped
title: We worked hard
type: bignumber
duration: 9
requires:
  - dataset: summary.totals
    fields: [commits]
    allow_partial: false
params:
  heading: "This year, we worked hard"
  value: summary.totals.commits
  label: "Commits"
  # Race up fast, then land the last five increments one at a time, each after a longer pause.
  count_ease: "expo.out"
  count_duration: 3.0
  count_tail: [0.25, 0.35, 0.5, 0.7, 1.0]
```
In `tests/scenes/test_build.py` change the expected `year-wrapped` durations from `[8.0, 6.0, 8.0, 8.0, 6.0, 10.0]` to `[9.0, 6.0, 8.0, 8.0, 6.0, 10.0]` (change only that list).

- [ ] **Step 7: Spec**

In `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`, section 13, in the `Initial types` line, change `optional count-up duration and ease)` (in the `bignumber` description) to `optional count-up duration, ease and tail beats)`.

- [ ] **Step 8: Run everything**

Run: `node --test tests-js/ && python3 -m pytest -q && PYTHONPATH=src python3 -m team_wrapped validate-script year-wrapped --data data-sample`
Expected: all pass; validate unchanged (six scenes).

- [ ] **Step 9: Syntax-check and build**

Run: `cp web/scene-types/bignumber/render.js "$TMPDIR/bignumber.mjs" && node --check "$TMPDIR/bignumber.mjs" && node --check web/presets/presets.js && PYTHONPATH=src python3 -m team_wrapped build year-wrapped --data data-sample --out "$TMPDIR/tw-tail"`
Expected: no syntax errors; `built .../tw-tail/year-wrapped/index.html`.

- [ ] **Step 10: Commit**

```bash
git add web tests-js scenes tests docs
git commit -m "Land the last increments of the opening count as slow beats" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Not in this plan

- Checking the feel in a browser: the controller samples the displayed number over time afterwards.
- Tail beats for other scenes or for the supporting figures.
