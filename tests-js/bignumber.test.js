const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const presets = require("../web/presets/presets.js");

// A minimal DOM: just enough for the renderer, which only builds elements.
function makeEl(tag) {
  const el = { tag, className: "", textContent: "", children: [] };
  el.append = (...kids) => { el.children.push(...kids); };
  el.appendChild = (kid) => { el.children.push(kid); return kid; };
  return el;
}

// Load render.js the way the build does: `export default` becomes an assignment.
function loadRenderer(type) {
  const file = path.join(__dirname, "..", "web", "scene-types", type, "render.js");
  const source = fs.readFileSync(file, "utf8").replace("export default", "module.exports =");
  const module = { exports: {} };
  new Function("module", "document", source)(module, { createElement: makeEl });
  return module.exports;
}

function fakeTimeline() {
  const calls = [];
  const tl = {
    calls,
    from: (targets, vars, at) => { calls.push({ kind: "from", targets, vars, at }); return tl; },
    to: (target, vars, at) => { calls.push({ kind: "to", target, vars, at }); return tl; },
  };
  return tl;
}

function find(el, className, found = []) {
  if (el.className === className) found.push(el);
  (el.children || []).forEach((kid) => find(kid, className, found));
  return found;
}

function render(params, data, partial = []) {
  const tl = fakeTimeline();
  const container = makeEl("section");
  const result = loadRenderer("bignumber").render({
    container, data, params, partial, duration: 6, gsap: { timeline: () => tl }, presets,
  });
  return { tl, container, result };
}

// Run every count-up to its end so the elements show their final text.
function finishCountUps(tl) {
  tl.calls.filter((c) => c.kind === "to").forEach((c) => { c.target.v = c.vars.v; c.vars.onUpdate(); });
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
