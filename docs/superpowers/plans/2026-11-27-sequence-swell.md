# Sequence Scene: Swell and Side Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the `sequence` scene (scene two), make each number swell past its final size and then settle back when it appears, and put each label to the right of its number (reviews with "Pull requests", then comments with "Comments").

**Architecture:** A new `swellIn` animation preset (appear, grow to a peak, contract to size 1); the `sequence` renderer uses it for number steps and fades the label in beside the number; CSS lays number and label out in a row.

**Tech Stack:** classic-script JavaScript renderer and presets tested with `node --test`, GSAP timelines (already vendored).

Builds on `2026-11-27-sequence-scene.md` (committed on the branch `feature/sequence-scene`, not yet merged).

## Global Constraints

- Renderers are classic scripts: exactly one `export default { render(ctx) }`, no `import`; `render(ctx)` returns a GSAP timeline and touches only `container`; data shown with `textContent` or element properties, never `innerHTML`.
- Numbers still appear at their final value (no count-up); text steps ("and left") keep their existing `popIn`.
- The step timing stays: step `i` starts at `0.8 + i * 1.0` seconds; the whole scene still fits its 6 s default duration.
- Run tests with `node --test tests-js/` and `python3 -m pytest -q`; never commit anything under `data/` or `dist/`.
- Commit trailer, as a separate `-m` paragraph: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## File Structure

```
web/presets/presets.js            # modify: swellIn
tests-js/presets.test.js          # modify: swellIn test
tests-js/helpers.js               # modify: fakeTimeline records fromTo
tests-js/sequence.test.js         # modify: new expectations
web/scene-types/sequence/render.js   # modify: swell + side label
web/player/player.css             # modify: row layout for a step
docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md   # modify: preset list
```

---

### Task 1: `swellIn` preset and side-by-side number and label

**Interfaces:**
- Consumes: `presets.fadeIn(tl, targets, at, duration)`, `presets.popIn`, `presets.format`, `presets.lookup`, `presets.isPartial` (existing); `tests-js/helpers.js` `{makeEl, loadRenderer, fakeTimeline, find, finishCountUps}`.
- Produces: `presets.swellIn(tl, target, at = 0, peak = 1.25, duration = 0.55)`: adds a `fromTo` tween (`{opacity: 0, scale: 0}` to `{opacity: 1, scale: peak}`, ease `power2.out`, duration `duration * 0.55`) at `at`, then a `to` tween (`{scale: 1}`, ease `power2.inOut`, duration `duration * 0.45`) at `at + duration * 0.55`; returns `tl`. The fake timeline in `helpers.js` also records `fromTo` calls as `{kind: "fromTo", targets, from, vars, at}`.

- [ ] **Step 1: Create the branch state check**

You continue on the existing branch `feature/sequence-scene` (already checked out). Confirm with `git branch --show-current`.
Expected: `feature/sequence-scene`

- [ ] **Step 2: Write the failing tests**

In `tests-js/helpers.js`, in `fakeTimeline`, add after the `from` entry:
```js
    fromTo: (targets, from, vars, at) => { calls.push({ kind: "fromTo", targets, from, vars, at }); return tl; },
```

In `tests-js/presets.test.js` append:
```js
test("swellIn appears, grows past its size and settles back to 1", () => {
  const calls = [];
  const tl = {
    fromTo: (t, from, vars, at) => { calls.push({ kind: "fromTo", from, vars, at }); return tl; },
    to: (t, vars, at) => { calls.push({ kind: "to", vars, at }); return tl; },
  };
  assert.strictEqual(presets.swellIn(tl, {}, 2, 1.25, 0.6), tl);
  assert.strictEqual(calls.length, 2);
  const [grow, settle] = calls;
  assert.deepStrictEqual(grow.from, { opacity: 0, scale: 0 });
  assert.strictEqual(grow.vars.opacity, 1);
  assert.strictEqual(grow.vars.scale, 1.25);
  assert.strictEqual(grow.at, 2);
  assert.strictEqual(settle.vars.scale, 1);
  assert.ok(Math.abs(settle.at - (2 + 0.6 * 0.55)) < 1e-9);
  assert.ok(Math.abs(grow.vars.duration + settle.vars.duration - 0.6) < 1e-9);
});
```

In `tests-js/sequence.test.js` make these changes:
- In the test "numbers show their final value immediately, without a count-up", replace the line `assert.strictEqual(tl.calls.filter((c) => c.kind === "to").length, 0);   // nothing counts up` with
```js
  assert.strictEqual(tl.calls.filter((c) => c.kind === "to" && "v" in c.vars).length, 0);   // nothing counts up
```
- Replace the whole test "each step pops in on its own, one after another" with these four tests (timings are sums of floats such as 0.8 + 0.15, so they are compared after rounding with this helper, which you also add once near the top of the file, after `PARAMS`: `const round2 = (n) => Math.round(n * 100) / 100;`):
```js
test("each number swells past its size and then settles back", () => {
  const { tl } = render(PARAMS, DATA);
  const swells = tl.calls.filter((c) => c.kind === "fromTo");
  assert.deepStrictEqual(swells.map((c) => round2(c.at)), [0.8, 2.8]);
  assert.ok(swells.every((c) => c.from.scale === 0 && c.from.opacity === 0 && c.vars.scale > 1));
  const settles = tl.calls.filter((c) => c.kind === "to" && c.vars.scale === 1);
  assert.strictEqual(settles.length, 2);
  settles.forEach((c, i) => assert.ok(c.at > swells[i].at));
});

test("each label fades in beside its number, a little after the number starts", () => {
  const { tl } = render(PARAMS, DATA);
  const fades = tl.calls.filter((c) => c.kind === "from" && !Array.isArray(c.targets));
  // the heading at 0, then the two labels
  assert.deepStrictEqual(fades.map((c) => round2(c.at)), [0, 0.95, 2.95]);
});

test("the text step pops in on its own between the two numbers", () => {
  const { tl } = render(PARAMS, DATA);
  const pops = tl.calls.filter((c) => c.kind === "from" && Array.isArray(c.targets) && c.targets.length === 1);
  assert.strictEqual(pops.length, 1);
  assert.strictEqual(round2(pops[0].at), 1.8);
  assert.ok(pops[0].vars.scale < 1 && pops[0].vars.opacity === 0);
});

test("a number step holds the number first and its label after it, to be laid out side by side", () => {
  const { container } = render(PARAMS, DATA);
  const steps = find(container, "tw-seq-body")[0].children.filter((c) => c.className === "tw-seq-step");
  steps.forEach((step) => {
    assert.deepStrictEqual(step.children.slice(0, 2).map((c) => c.className), ["tw-seq-value", "tw-seq-label"]);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `node --test tests-js/`
Expected: FAIL: `presets.swellIn is not a function` and the sequence tests (no `fromTo` swells yet, label fades at the wrong times).

- [ ] **Step 4: Add the preset**

In `web/presets/presets.js`, add after `popIn` (before `bubbleIn`) and add `swellIn` to the exported `api` object:
```js
  // The element appears, swells past its final size, then settles back ("expand a bit, then contract a bit").
  function swellIn(tl, target, at = 0, peak = 1.25, duration = 0.55) {
    tl.fromTo(target, { opacity: 0, scale: 0 }, { opacity: 1, scale: peak, duration: duration * 0.55, ease: "power2.out" }, at);
    return tl.to(target, { scale: 1, duration: duration * 0.45, ease: "power2.inOut" }, at + duration * 0.55);
  }
```

- [ ] **Step 5: Update the renderer**

In `web/scene-types/sequence/render.js`, replace the final line inside the `steps.forEach` callback `presets.popIn(tl, [el], 0.8 + i * 1.0, 0, 0.5);` and the lines just above it so the end of the callback reads:
```js
      body.append(el);
      const at = 0.8 + i * 1.0;
      if (typeof step.text === "string") {
        presets.popIn(tl, [el], at, 0, 0.5);
      } else {
        // The number swells and settles; its label fades in beside it a moment later.
        presets.swellIn(tl, el.children[0], at);
        presets.fadeIn(tl, el.children[1], at + 0.15, 0.4);
      }
```
(`el.children[0]` is the `tw-seq-value` element and `el.children[1]` the `tw-seq-label`, as built a few lines above; the partial badge, if any, is a later child and is left alone.)

- [ ] **Step 6: Lay the step out as a row**

In `web/player/player.css`, replace the existing `.tw-seq-value`, `.tw-seq-label` and `.tw-seq-partial` rules (keep `.tw-seq-text` and the other `.tw-seq*` rules as they are) with these four rules:
```css
.tw-seq-step { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: center; column-gap: 1.2rem; }
.tw-seq-value { font-size: clamp(3.5rem, 13vw, 8rem); font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }
.tw-seq-label { font-size: clamp(1.1rem, 3vw, 1.8rem); opacity: 0.8; }
.tw-seq-partial { flex-basis: 100%; text-align: center; margin-top: 0.3rem; font-size: 0.75rem; color: #e6b450; }
```
(the badge, if any, sits on its own line under the row).

- [ ] **Step 7: Update the spec**

In `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`, section 13, in the "Animation presets" paragraph, add `swell-in` (appear, grow past the final size, settle back) to the list of presets (next to `bubble-in`).

- [ ] **Step 8: Run everything**

Run: `node --test tests-js/ && python3 -m pytest -q`
Expected: all pass. JS: the previous 38 plus 1 new preset test and 3 net new sequence tests: report the exact count.

- [ ] **Step 9: Syntax-check and build**

Run: `cp web/scene-types/sequence/render.js "$TMPDIR/sequence.mjs" && node --check "$TMPDIR/sequence.mjs" && PYTHONPATH=src python3 -m team_wrapped build year-wrapped --data data-sample --out "$TMPDIR/tw-swell"`
Expected: no syntax errors; `built .../tw-swell/year-wrapped/index.html`.

- [ ] **Step 10: Commit**

```bash
git add web tests-js docs
git commit -m "Swell the sequence numbers and put each label beside its number" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Not in this plan

- Playing the scene in a browser: the controller checks the swell and the layout by hand afterwards.
