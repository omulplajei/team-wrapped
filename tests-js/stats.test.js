const test = require("node:test");
const assert = require("node:assert");
const presets = require("../web/presets/presets.js");
const { makeEl, loadRenderer, fakeTimeline, find } = require("./helpers.js");

const DATA = {
  "summary.totals": { commits: 1240, merged_prs: 310 },
  "delivery_volume.lines": { total_net: 26850 },
};
const PARAMS = {
  items: [
    { label: "Commits", value: "summary.totals.commits" },
    { label: "Merged pull requests", value: "summary.totals.merged_prs" },
    { label: "Net lines of change", value: "delivery_volume.lines.total_net" },
  ],
};
const round2 = (n) => Math.round(n * 100) / 100;

function render(params, data = DATA, partial = []) {
  const tl = fakeTimeline();
  const container = makeEl("section");
  const result = loadRenderer("stats").render({
    container, data, params, partial, duration: 8, gsap: { timeline: () => tl }, presets,
  });
  return { tl, container, result };
}

const countTimes = (tl) => tl.calls.filter((c) => c.kind === "to" && "v" in c.vars).map((c) => round2(c.at));

test("without a heading the grid is placed directly in the scene, as before", () => {
  const { tl, container, result } = render(PARAMS);
  assert.strictEqual(result, tl);
  assert.strictEqual(container.children.length, 1);
  assert.strictEqual(container.children[0].className, "tw-stats");
  assert.strictEqual(find(container, "tw-stat").length, 3);
  assert.deepStrictEqual(countTimes(tl), [0.3, 0.45, 0.6]);
  const stagger = tl.calls.find((c) => c.kind === "from" && Array.isArray(c.targets));
  assert.strictEqual(round2(stagger.at), 0);
});

test("an optional heading sits above the grid at the top of the scene", () => {
  const { container } = render({ ...PARAMS, heading: "Year in numbers" });
  const wrap = container.children[0];
  assert.strictEqual(wrap.className, "tw-stats-scene");
  assert.deepStrictEqual(wrap.children.map((c) => c.className), ["tw-stats-heading", "tw-stats"]);
  assert.strictEqual(wrap.children[0].textContent, "Year in numbers");
  assert.strictEqual(find(container, "tw-stat").length, 3);
});

test("a heading fades in first and delays the cards and their count-ups by half a second", () => {
  const { tl, container } = render({ ...PARAMS, heading: "Year in numbers" });
  const heading = find(container, "tw-stats-heading")[0];
  const fade = tl.calls.find((c) => c.kind === "from" && c.targets === heading);
  assert.ok(fade);
  assert.strictEqual(round2(fade.at), 0);
  assert.deepStrictEqual(countTimes(tl), [0.8, 0.95, 1.1]);                       // 0.5 s later than without a heading
  const stagger = tl.calls.find((c) => c.kind === "from" && Array.isArray(c.targets));
  assert.strictEqual(round2(stagger.at), 0.5);
});

test("an empty or non-string heading adds no heading and no delay", () => {
  [{ heading: "" }, { heading: 5 }].forEach((extra) => {
    const { tl, container } = render({ ...PARAMS, ...extra });
    assert.strictEqual(container.children[0].className, "tw-stats");
    assert.strictEqual(find(container, "tw-stats-heading").length, 0);
    assert.deepStrictEqual(countTimes(tl), [0.3, 0.45, 0.6]);
  });
});

test("values, missing values and partial labels still work with a heading", () => {
  const { container } = render({ ...PARAMS, heading: "H" }, { "summary.totals": { commits: 5 } }, ["summary.totals"]);
  const values = find(container, "tw-stat-value").map((e) => e.textContent);
  assert.strictEqual(values[1], "–");                                              // merged_prs is missing
  assert.strictEqual(find(container, "tw-stat-partial").length, 2);                // commits and merged_prs refs
});
