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

function render(params, data, elDefaults = {}) {
  const tl = fakeTimeline();
  const container = makeEl("section");
  const result = loadRenderer("repogrid", elDefaults).render({
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

test("the folder size is fitted to the measured space, with size classes as the fallback", () => {
  const defaults = { clientWidth: 900, clientHeight: 600, offsetTop: 24, offsetHeight: 60 };
  const grid = render(PARAMS, dataFor(NAMES), defaults).container.children[0].children[1];
  const fit = presets.fitFolderSize(3, 900, 600 - 24 - 60 - 24);
  assert.strictEqual(grid.style["--tw-folder"], fit.size + "px");
  assert.strictEqual(grid.style["--tw-folder-font"], fit.font + "px");
  const bare = render(PARAMS, dataFor(NAMES)).container.children[0].children[1];
  assert.strictEqual(bare.style["--tw-folder"], undefined);
});

test("the folder size fit is discriminating with many repositories and constrained space", () => {
  // With 45 repos, constrained dimensions, and a 1120 width cap in render.js:
  // availW = min(1500, 1120) = 1120, availH = 682 - 24 - 60 - 24 = 574
  // Fit formula: sizes 128→36 step 2; gapX = size*0.14; gapY = size*0.2
  // cols = max(1, floor((1120 + gapX)/(size + gapX))); rows = ceil(45/cols)
  // needed = rows*size*0.75 + (rows-1)*gapY
  // For size=112: gapX=15.68, gapY=22.4, cols=8, rows=6, needed=6*84+5*22.4=616 > 574 (too big)
  // For size=110: gapX=15.4, gapY=22, cols=9, rows=5, needed=5*82.5+4*22=500.5 <= 574 (fits)
  // font = max(5, round(110*0.1*10)/10) = max(5, 11) = 11
  const names = Array.from({ length: 45 }, (_, i) => `repo-${i}`);
  const defaults = { clientWidth: 1500, clientHeight: 682, offsetTop: 24, offsetHeight: 60 };
  const grid = render(PARAMS, dataFor(names), defaults).container.children[0].children[1];
  assert.strictEqual(grid.style["--tw-folder"], "110px");
  assert.strictEqual(grid.style["--tw-folder-font"], "11px");
});

test("the folder size is not set when the container has no measurable dimensions", () => {
  const names = Array.from({ length: 3 }, (_, i) => `repo-${i}`);
  const defaults = { clientWidth: 0, clientHeight: 0, offsetTop: 0, offsetHeight: 0 };
  const grid = render(PARAMS, dataFor(names), defaults).container.children[0].children[1];
  assert.strictEqual(grid.style["--tw-folder"], undefined);
  assert.strictEqual(grid.style["--tw-folder-font"], undefined);
  assert.strictEqual(grid.className, "tw-folders tw-folders-lg");
});
