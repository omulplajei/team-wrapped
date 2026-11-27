const test = require("node:test");
const assert = require("node:assert");
const presets = require("../web/presets/presets.js");
const { makeEl, loadRenderer, fakeTimeline, find } = require("./helpers.js");

const DATA = {
  "curiosities.longest_comment_chain": [
    { value: 23, repo: "sample-api", pr_number: 482 },
    { value: 19, repo: "sample-web", pr_number: 1203 },
  ],
};
const PARAMS = {
  teaser: "The longest conversation",
  records: "curiosities.longest_comment_chain",
  unit: "comments in one review thread",
  context: "in {repo}, pull request #{pr_number}",
};
const round2 = (n) => Math.round(n * 100) / 100;

function render(params, data = DATA, partial = []) {
  const tl = fakeTimeline();
  const container = makeEl("section");
  const result = loadRenderer("curiosity").render({
    container, data, params, partial, duration: 6, gsap: { timeline: () => tl }, presets,
  });
  return { tl, container, result };
}

test("the scene shows the teaser, the first record's number, the unit and the filled context", () => {
  const { tl, container, result } = render(PARAMS);
  assert.strictEqual(result, tl);
  const wrap = container.children[0];
  assert.strictEqual(wrap.className, "tw-cur");
  assert.deepStrictEqual(wrap.children.map((c) => c.className), ["tw-cur-teaser", "tw-cur-value", "tw-cur-unit", "tw-cur-context"]);
  assert.deepStrictEqual(wrap.children.map((c) => c.textContent), [
    "The longest conversation", "23", "comments in one review thread", "in sample-api, pull request #482",
  ]);
});

test("the number appears at its final value and swells, with no count-up", () => {
  const { tl, container } = render(PARAMS);
  assert.strictEqual(tl.calls.filter((c) => c.kind === "to" && "v" in c.vars).length, 0);
  const swells = tl.calls.filter((c) => c.kind === "fromTo");
  assert.strictEqual(swells.length, 1);
  assert.strictEqual(swells[0].targets, find(container, "tw-cur-value")[0]);
  assert.strictEqual(round2(swells[0].at), 0.9);
  assert.ok(swells[0].vars.scale > 1);
});

test("the teaser, unit and context fade in one after another", () => {
  const { tl, container } = render(PARAMS);
  const fades = tl.calls.filter((c) => c.kind === "from" && !Array.isArray(c.targets));
  assert.deepStrictEqual(fades.map((c) => c.targets.className), ["tw-cur-teaser", "tw-cur-unit", "tw-cur-context"]);
  assert.deepStrictEqual(fades.map((c) => round2(c.at)), [0, 1.35, 1.85]);
});

test("a different value_key picks another number from the record", () => {
  const data = { "curiosities.busiest_day": [{ value: 87, merged_prs: 12, date: "2026-03-14" }] };
  const { container } = render({ teaser: "T", records: "curiosities.busiest_day", unit: "pull requests merged", value_key: "merged_prs", context: "on {date}" }, data);
  assert.strictEqual(find(container, "tw-cur-value")[0].textContent, "12");
  assert.strictEqual(find(container, "tw-cur-context")[0].textContent, "on Saturday 14 March");
});

test("no context param means no context element", () => {
  const { container } = render({ teaser: "T", records: PARAMS.records, unit: "u" });
  assert.strictEqual(find(container, "tw-cur-context").length, 0);
});

test("a missing record shows a dash and no context", () => {
  [{}, { "curiosities.longest_comment_chain": [] }, { "curiosities.longest_comment_chain": "x" }].forEach((data) => {
    const { container } = render(PARAMS, data);
    assert.strictEqual(find(container, "tw-cur-value")[0].textContent, "–");
    assert.strictEqual(find(container, "tw-cur-context")[0].textContent, "");
  });
});

test("a partial dataset gets a badge that fades in with the unit", () => {
  const { tl, container } = render(PARAMS, DATA, ["curiosities.longest_comment_chain"]);
  const badge = find(container, "tw-cur-partial")[0];
  assert.ok(badge);
  const fade = tl.calls.find((c) => c.kind === "from" && Array.isArray(c.targets) && c.targets.includes(badge));
  assert.strictEqual(round2(fade.at), 1.35);
  assert.strictEqual(find(render(PARAMS, DATA, []).container, "tw-cur-partial").length, 0);
});

test("the fades use the teaser, unit and context durations", () => {
  const { tl } = render(PARAMS);
  const fades = tl.calls.filter((c) => c.kind === "from" && !Array.isArray(c.targets));
  assert.deepStrictEqual(fades.map((c) => c.vars.duration), [0.6, 0.4, 0.5]);
});

test("a 4-digit pr_number prints without a thousands separator", () => {
  const data = { "curiosities.longest_comment_chain": [{ value: 9, repo: "sample-api", pr_number: 4821 }] };
  const { container } = render(PARAMS, data);
  assert.strictEqual(find(container, "tw-cur-context")[0].textContent, "in sample-api, pull request #4821");
});

const ONE = { "curiosities.longest_comment_chain": [{ value: 1, repo: "sample-api", pr_number: 7, from: "2026-03-02" }] };
const SING = { unit_one: "comment in one review thread", context_one: "on {from}" };

test("unit_one and context_one are used when the number is exactly 1", () => {
  const { container } = render({ ...PARAMS, ...SING }, ONE);
  assert.strictEqual(find(container, "tw-cur-unit")[0].textContent, "comment in one review thread");
  assert.strictEqual(find(container, "tw-cur-context")[0].textContent, "on 2 March");
});

test("unit_one and context_one are ignored when the number is not 1", () => {
  const { container } = render({ ...PARAMS, ...SING });
  assert.strictEqual(find(container, "tw-cur-unit")[0].textContent, "comments in one review thread");
  assert.strictEqual(find(container, "tw-cur-context")[0].textContent, "in sample-api, pull request #482");
});

test("a value of 1 falls back to unit and context when the singular forms are missing or empty", () => {
  const onlyUnit = render({ ...PARAMS, unit_one: "comment" }, ONE).container;
  assert.strictEqual(find(onlyUnit, "tw-cur-unit")[0].textContent, "comment");
  assert.strictEqual(find(onlyUnit, "tw-cur-context")[0].textContent, "in sample-api, pull request #7");
  const onlyContext = render({ ...PARAMS, context_one: "on {from}", unit_one: "" }, ONE).container;
  assert.strictEqual(find(onlyContext, "tw-cur-unit")[0].textContent, "comments in one review thread");
  assert.strictEqual(find(onlyContext, "tw-cur-context")[0].textContent, "on 2 March");
});
