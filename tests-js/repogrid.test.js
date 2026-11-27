const test = require("node:test");
const assert = require("node:assert");
const presets = require("../web/presets/presets.js");
const { makeEl, loadRenderer, fakeTimeline, find, finishCountUps } = require("./helpers.js");

const NAMES = ["alpha-api", "beta-web", "gamma-docs"];
const dataFor = (names) => ({
  "repos.touched": { total: names.length, list: names.map((name) => ({ name })) },
});
const PARAMS = {
  heading: "Across {count} repositories",
  heading_one: "Across {count} repository",
  value: "repos.touched.total",
  names: "repos.touched.list",
};

function render(params, data) {
  const tl = fakeTimeline();
  const container = makeEl("section");
  const result = loadRenderer("repogrid").render({
    container, data, params, partial: [], duration: 8, gsap: { timeline: () => tl }, presets,
  });
  return { tl, container, result };
}

test("the heading wraps the highlighted count in its own element", () => {
  const { tl, container, result } = render(PARAMS, dataFor(NAMES));
  assert.strictEqual(result, tl);
  finishCountUps(tl);
  const texts = find(container, "tw-repos-text").map((e) => e.textContent);
  assert.deepStrictEqual(texts, ["Across ", " repositories"]);
  assert.strictEqual(find(container, "tw-repos-count")[0].textContent, "3");
});

test("a single repository uses the singular heading", () => {
  const { tl, container } = render(PARAMS, dataFor(["only-one"]));
  finishCountUps(tl);
  const texts = find(container, "tw-repos-text").map((e) => e.textContent);
  assert.deepStrictEqual(texts, ["Across ", " repository"]);
  assert.strictEqual(find(container, "tw-repos-count")[0].textContent, "1");
});

test("there is one folder per repository with its name inside", () => {
  const { container } = render(PARAMS, dataFor(NAMES));
  const folders = find(container, "tw-folder");
  assert.strictEqual(folders.length, 3);
  assert.deepStrictEqual(find(container, "tw-folder-name").map((e) => e.textContent), NAMES);
  assert.deepStrictEqual(folders.map((f) => f.title), NAMES);
});

test("the folder size class follows the number of repositories", () => {
  const many = (n) => Array.from({ length: n }, (_, i) => `repo-${i}`);
  assert.strictEqual(render(PARAMS, dataFor(many(3))).container.children[0].children[1].className, "tw-folders tw-folders-lg");
  assert.strictEqual(render(PARAMS, dataFor(many(20))).container.children[0].children[1].className, "tw-folders tw-folders-md");
  assert.strictEqual(render(PARAMS, dataFor(many(40))).container.children[0].children[1].className, "tw-folders tw-folders-sm");
});

test("the folders bubble in with a stagger that keeps the whole entrance short", () => {
  const small = render(PARAMS, dataFor(NAMES)).tl.calls.filter((c) => c.kind === "from");
  const bubble = small.find((c) => Array.isArray(c.targets) && c.targets.length === 3);
  assert.ok(bubble);
  assert.strictEqual(bubble.vars.stagger, 0.12);
  const names = Array.from({ length: 50 }, (_, i) => `repo-${i}`);
  const big = render(PARAMS, dataFor(names)).tl.calls.filter((c) => c.kind === "from");
  const crowd = big.find((c) => Array.isArray(c.targets) && c.targets.length === 50);
  assert.ok(crowd.vars.stagger * 50 <= 2.5 + 1e-9);
});

test("no repositories shows the heading with 0 and no grid", () => {
  const { tl, container } = render(PARAMS, dataFor([]));
  finishCountUps(tl);
  assert.strictEqual(find(container, "tw-repos-count")[0].textContent, "0");
  assert.strictEqual(find(container, "tw-folder").length, 0);
  assert.strictEqual(container.children[0].children.length, 1);
});

test("a missing count shows a dash", () => {
  const { container } = render(PARAMS, {});
  assert.strictEqual(find(container, "tw-repos-count")[0].textContent, "–");
});
