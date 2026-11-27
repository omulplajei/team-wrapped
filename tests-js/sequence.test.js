const test = require("node:test");
const assert = require("node:assert");
const presets = require("../web/presets/presets.js");
const { makeEl, loadRenderer, fakeTimeline, find } = require("./helpers.js");

const DATA = { "summary.totals": { reviews: 540, comments: 1180 } };
const PARAMS = {
  heading: "We look after each other",
  steps: [
    { lead: "We merged", value: "summary.totals.reviews", label: "Pull requests" },
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
  assert.deepStrictEqual(find(container, "tw-seq-lead").map((e) => e.textContent), ["We merged", "and left"]);
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
