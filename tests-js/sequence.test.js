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
  assert.strictEqual(tl.calls.filter((c) => c.kind === "to" && "v" in c.vars).length, 0);   // nothing counts up
});

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

test("a missing value shows a dash", () => {
  const { container } = render(PARAMS, {});
  assert.deepStrictEqual(find(container, "tw-seq-value").map((e) => e.textContent), ["–", "–"]);
});

test("partial datasets are labelled on the number steps", () => {
  const { container } = render(PARAMS, DATA, ["summary.totals"]);
  assert.strictEqual(find(container, "tw-seq-partial").length, 2);
  assert.strictEqual(find(render(PARAMS, DATA, []).container, "tw-seq-partial").length, 0);
});
