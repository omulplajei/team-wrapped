const test = require("node:test");
const assert = require("node:assert");
const presets = require("../web/presets/presets.js");
const { makeEl, loadRenderer, fakeTimeline, find, finishCountUps } = require("./helpers.js");

function render(params, data, partial = []) {
  const tl = fakeTimeline();
  const container = makeEl("section");
  const result = loadRenderer("bignumber").render({
    container, data, params, partial, duration: 6, gsap: { timeline: () => tl }, presets,
  });
  return { tl, container, result };
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
