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
