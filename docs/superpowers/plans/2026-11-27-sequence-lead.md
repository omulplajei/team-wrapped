# Sequence Scene: Lead Text and Accent Numbers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In scene two, show two lines, each "lead text, number, label" on one line: "We raised **540** Pull requests" and "and left **1,180** Comments", with the numbers in the theme's accent colour (a different colour from the text).

**Architecture:** A number step in the `sequence` scene type may carry an optional `lead` text that is laid out on the same row, before the number. The renderer is rewritten with named elements instead of child indices; the lead fades in first, then the number swells, then the label. The number colour comes from `--tw-accent`.

**Tech Stack:** classic-script JavaScript renderer tested with `node --test`, GSAP timelines, CSS variables from the theme system.

Builds on `2026-11-27-sequence-scene.md` and `2026-11-27-sequence-swell.md` (both on `main`).

## Global Constraints

- Renderers are classic scripts: exactly one `export default { render(ctx) }`, no `import`; `render(ctx)` returns a GSAP timeline and touches only `container`; data shown with `textContent`, never `innerHTML`.
- Numbers appear at their final value (no count-up); they swell past their size and settle back (`presets.swellIn`); a label (and the partial badge) fades in only after the number has settled, so nothing overlaps the swollen number.
- The standalone `{text: ...}` step type keeps working (used by other scenes), including its `popIn`.
- All colours come from the theme variables: numbers use `var(--tw-accent)`; no hard-coded colours in `player.css` outside the `:root` block.
- Shared scenes are scope-agnostic; no new dataset; the scene id `we-looked-after-each-other` stays.
- Run tests with `node --test tests-js/` and `python3 -m pytest -q`; never commit anything under `data/` or `dist/`; do not read or touch `data/` or `.claude/`.
- Commit trailer, as a separate `-m` paragraph: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## File Structure

```
web/scene-types/sequence/render.js    # modify: lead text, named elements, new timing
web/player/player.css                 # modify: lead style, accent-coloured numbers
tests-js/sequence.test.js             # modify: new expectations
scenes/we-looked-after-each-other.yml # modify: two lead steps
docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md   # modify: sequence step description
```

---

### Task 1: Lead text, accent numbers, one line per step

**Interfaces:**
- Consumes: `presets.fadeIn(tl, targets, at, duration)`, `presets.swellIn(tl, target, at)`, `presets.popIn`, `presets.format`, `presets.lookup`, `presets.isPartial`; `tests-js/helpers.js` `{makeEl, loadRenderer, fakeTimeline, find}`.
- Produces: `sequence` step shape `{lead?: string, value: <data reference>, label: string}` (number step) or `{text: string}` (text step). A number step element has class `tw-seq-step` and holds, in this order: `tw-seq-lead` (only when `lead` is set), `tw-seq-value`, `tw-seq-label`, `tw-seq-partial` (only for partial data). Step `i` starts at `0.8 + i * 1.4` s. In a number step: the lead fades in at `at` (0.4 s); the number swells at `numberAt = at + 0.3` when there is a lead, else at `at`; the label and badge fade in at `numberAt + 0.45` (0.4 s).

- [ ] **Step 1: Create the branch**

```bash
git checkout -b feature/sequence-lead
```
Expected: `Switched to a new branch 'feature/sequence-lead'`

- [ ] **Step 2: Replace the tests (they fail first)**

Replace the whole content of `tests-js/sequence.test.js` with:
```js
const test = require("node:test");
const assert = require("node:assert");
const presets = require("../web/presets/presets.js");
const { makeEl, loadRenderer, fakeTimeline, find } = require("./helpers.js");

const DATA = { "summary.totals": { reviews: 540, comments: 1180 } };
const PARAMS = {
  heading: "We look after each other",
  steps: [
    { lead: "We raised", value: "summary.totals.reviews", label: "Pull requests" },
    { lead: "and left", value: "summary.totals.comments", label: "Comments" },
  ],
};
// The older shape: number steps without a lead, with a standalone text step between them.
const TEXT_PARAMS = {
  heading: "H",
  steps: [
    { value: "summary.totals.reviews", label: "Pull requests" },
    { text: "and left" },
    { value: "summary.totals.comments", label: "Comments" },
  ],
};
const round2 = (n) => Math.round(n * 100) / 100;

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

test("each step is one line: lead text, then the number, then its label", () => {
  const { container } = render(PARAMS, DATA);
  const body = find(container, "tw-seq-body")[0];
  assert.deepStrictEqual(body.children.map((s) => s.className), ["tw-seq-step", "tw-seq-step"]);
  body.children.forEach((step) => {
    assert.deepStrictEqual(step.children.map((c) => c.className), ["tw-seq-lead", "tw-seq-value", "tw-seq-label"]);
  });
  assert.deepStrictEqual(find(container, "tw-seq-lead").map((e) => e.textContent), ["We raised", "and left"]);
});

test("numbers show their final value immediately, without a count-up", () => {
  const { tl, container } = render(PARAMS, DATA);
  assert.deepStrictEqual(find(container, "tw-seq-value").map((e) => e.textContent), ["540", "1,180"]);
  assert.deepStrictEqual(find(container, "tw-seq-label").map((e) => e.textContent), ["Pull requests", "Comments"]);
  assert.strictEqual(tl.calls.filter((c) => c.kind === "to" && "v" in c.vars).length, 0);   // nothing counts up
});

test("each number swells past its size, after its lead text, and then settles back", () => {
  const { tl } = render(PARAMS, DATA);
  const swells = tl.calls.filter((c) => c.kind === "fromTo");
  assert.deepStrictEqual(swells.map((c) => round2(c.at)), [1.1, 2.5]);          // step start 0.8 / 2.2, plus 0.3
  assert.deepStrictEqual(swells.map((c) => c.targets.className), ["tw-seq-value", "tw-seq-value"]);
  assert.ok(swells.every((c) => c.from.scale === 0 && c.from.opacity === 0 && c.vars.scale > 1));
  const settles = tl.calls.filter((c) => c.kind === "to" && c.vars.scale === 1);
  assert.strictEqual(settles.length, 2);
  settles.forEach((c, i) => assert.ok(c.at > swells[i].at));
});

test("the lead fades in first and the label last, once the number has settled", () => {
  const { tl } = render(PARAMS, DATA);
  const fades = tl.calls.filter((c) => c.kind === "from" && !Array.isArray(c.targets));
  assert.deepStrictEqual(fades.map((c) => c.targets.className),
    ["tw-seq-heading", "tw-seq-lead", "tw-seq-label", "tw-seq-lead", "tw-seq-label"]);
  assert.deepStrictEqual(fades.map((c) => round2(c.at)), [0, 0.8, 1.55, 2.2, 2.95]);
});

test("the partial badge fades in with its label and is never shown un-animated", () => {
  const { tl, container } = render(PARAMS, DATA, ["summary.totals"]);
  const badges = find(container, "tw-seq-partial");
  assert.strictEqual(badges.length, 2);
  const has = (c, b) => (Array.isArray(c.targets) ? c.targets : [c.targets]).includes(b);
  const froms = tl.calls.filter((c) => c.kind === "from");
  badges.forEach((b) => assert.ok(froms.some((c) => has(c, b))));
  const times = froms.filter((c) => badges.some((b) => has(c, b))).map((c) => round2(c.at));
  assert.deepStrictEqual(times, [1.55, 2.95]);
  badges.forEach((b, i) => assert.strictEqual(b.className, "tw-seq-partial"));
});

test("a number step without a lead has no lead element", () => {
  const { container } = render(TEXT_PARAMS, DATA);
  assert.strictEqual(find(container, "tw-seq-lead").length, 0);
  const steps = find(container, "tw-seq-body")[0].children.filter((c) => c.className === "tw-seq-step");
  steps.forEach((step) => assert.deepStrictEqual(step.children.map((c) => c.className), ["tw-seq-value", "tw-seq-label"]));
});

test("a standalone text step still pops in on its own between number steps", () => {
  const { tl, container } = render(TEXT_PARAMS, DATA);
  const body = find(container, "tw-seq-body")[0];
  assert.deepStrictEqual(body.children.map((s) => s.className), ["tw-seq-step", "tw-seq-text", "tw-seq-step"]);
  assert.strictEqual(body.children[1].textContent, "and left");
  const pops = tl.calls.filter((c) => c.kind === "from" && Array.isArray(c.targets) && c.targets.length === 1);
  assert.strictEqual(pops.length, 1);
  assert.strictEqual(round2(pops[0].at), 2.2);
  assert.ok(pops[0].vars.scale < 1 && pops[0].vars.opacity === 0);
  const swells = tl.calls.filter((c) => c.kind === "fromTo");
  assert.deepStrictEqual(swells.map((c) => round2(c.at)), [0.8, 3.6]);          // no lead: no extra delay
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

- [ ] **Step 3: Run the tests to verify they fail**

Run: `node --test tests-js/sequence.test.js`
Expected: FAIL (no lead element yet, timings differ).

- [ ] **Step 4: Rewrite the renderer**

Replace the whole content of `web/scene-types/sequence/render.js` with:
```js
export default {
  render(ctx) {
    const { container, data, params, partial, gsap, presets } = ctx;
    const tl = gsap.timeline();

    const wrap = document.createElement("div");
    wrap.className = "tw-seq";

    const part = (className, text) => {
      const el = document.createElement("div");
      el.className = className;
      el.textContent = text;
      return el;
    };

    const heading = part("tw-seq-heading", params.heading);
    wrap.append(heading);
    presets.fadeIn(tl, heading, 0, 0.6);

    const body = document.createElement("div");
    body.className = "tw-seq-body";
    const steps = Array.isArray(params.steps) ? params.steps : [];

    steps.forEach((step, i) => {
      const at = 0.8 + i * 1.4;

      if (typeof step.text === "string") {
        const text = part("tw-seq-text", step.text);
        body.append(text);
        presets.popIn(tl, [text], at, 0, 0.5);
        return;
      }

      const el = document.createElement("div");
      el.className = "tw-seq-step";
      const lead = typeof step.lead === "string" ? part("tw-seq-lead", step.lead) : null;
      const raw = presets.lookup(data, step.value);
      // Shown at its final value straight away: the swell is the only animation.
      const value = part("tw-seq-value", typeof raw === "number" ? presets.format(raw) : "–");
      const label = part("tw-seq-label", step.label);
      const badge = presets.isPartial(partial, step.value) ? part("tw-seq-partial", "partial data") : null;
      el.append(...[lead, value, label, badge].filter(Boolean));
      body.append(el);

      // The lead text comes first, then the number swells and settles, and the label (with the
      // partial badge, if any) fades in last, once the number is back to size.
      if (lead) presets.fadeIn(tl, lead, at, 0.4);
      const numberAt = at + (lead ? 0.3 : 0);
      presets.swellIn(tl, value, numberAt);
      presets.fadeIn(tl, badge ? [label, badge] : label, numberAt + 0.45, 0.4);
    });

    wrap.append(body);
    container.append(wrap);
    return tl;
  },
};
```

- [ ] **Step 5: Style the lead and the numbers**

In `web/player/player.css`, change the `.tw-seq-value` rule to add the accent colour:
```css
.tw-seq-value { font-size: clamp(3.5rem, 13vw, 8rem); font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; color: var(--tw-accent); }
```
and add this rule next to the other `.tw-seq-*` rules:
```css
.tw-seq-lead { font-size: clamp(1.4rem, 4vw, 2.4rem); font-weight: 600; opacity: 0.9; }
```

- [ ] **Step 6: Update scene two and the spec**

Replace the `steps` list in `scenes/we-looked-after-each-other.yml` with:
```yaml
  steps:
    - {lead: "We raised", value: summary.totals.reviews, label: "Pull requests"}
    - {lead: "and left", value: summary.totals.comments, label: "Comments"}
```
In `docs/superpowers/specs/2026-11-25-team-wrapped-data-design.md`, section 13, in the `Initial types` line, change ``sequence` (a heading and a list of steps, each a number with a label or a plain text, popping in one by one)` so it reads `` `sequence` (a heading and a list of steps, each a number with a label and an optional lead text on the same line, or a plain text, appearing one by one)``.

- [ ] **Step 7: Run everything**

Run: `node --test tests-js/ && python3 -m pytest -q && PYTHONPATH=src python3 -m team_wrapped validate-script year-wrapped --data data-sample && grep -nE '#[0-9a-fA-F]{3,8}\b' web/player/player.css`
Expected: all tests pass; the validate output lists six scenes with `we-looked-after-each-other: supported`; the grep lists only lines inside the `:root` block.

- [ ] **Step 8: Syntax-check and build**

Run: `cp web/scene-types/sequence/render.js "$TMPDIR/sequence.mjs" && node --check "$TMPDIR/sequence.mjs" && PYTHONPATH=src python3 -m team_wrapped build year-wrapped --data data-sample --out "$TMPDIR/tw-lead"`
Expected: no syntax errors; `built .../tw-lead/year-wrapped/index.html`.

- [ ] **Step 9: Commit**

```bash
git add web tests-js scenes docs
git commit -m "Put lead text, number and label on one line and colour the numbers" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Not in this plan

- Playing the scene in a browser: the controller checks the layout and colours by hand afterwards.
- Changing what the 540 figure counts: it is the number of reviews (see the summary to the user).
