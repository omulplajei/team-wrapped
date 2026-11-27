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

test("an optional heading sits above the number", () => {
  const { container } = render({ ...PARAMS, heading: "This year, we worked hard" }, DATA);
  const wrap = container.children[0];
  assert.strictEqual(wrap.className, "tw-hero");
  assert.deepStrictEqual(wrap.children.slice(0, 3).map((c) => c.className),
    ["tw-hero-heading", "tw-hero-value", "tw-hero-label"]);
  assert.strictEqual(wrap.children[0].textContent, "This year, we worked hard");
});

test("without a heading there is no heading element", () => {
  const { container } = render(PARAMS, DATA);
  assert.strictEqual(find(container, "tw-hero-heading").length, 0);
});

test("a heading delays the count-ups so it can be read first", () => {
  const round2 = (n) => Math.round(n * 100) / 100;
  const counts = (params) => render(params, DATA).tl.calls
    .filter((c) => c.kind === "to" && "v" in c.vars).map((c) => round2(c.at));
  assert.deepStrictEqual(counts(PARAMS), [0.3, 2.8]);                                   // unchanged without a heading
  assert.deepStrictEqual(counts({ ...PARAMS, heading: "H" }), [1.0, 3.5]);             // everything 0.7 s later
});

test("a heading delays the supporting cards' pop-in together with their numbers", () => {
  const round2 = (n) => Math.round(n * 100) / 100;
  const popAt = (params) => {
    const cards = render(params, DATA).tl.calls.find((c) => c.kind === "from" && Array.isArray(c.targets));
    return round2(cards.at);
  };
  assert.strictEqual(popAt(PARAMS), 2.8);
  assert.strictEqual(popAt({ ...PARAMS, heading: "H" }), 3.5);
});

test("an empty heading adds no element and no delay", () => {
  const round2 = (n) => Math.round(n * 100) / 100;
  const { tl, container } = render({ ...PARAMS, heading: "" }, DATA);
  assert.strictEqual(find(container, "tw-hero-heading").length, 0);
  assert.deepStrictEqual(tl.calls.filter((c) => c.kind === "to" && "v" in c.vars).map((c) => round2(c.at)), [0.3, 2.8]);
});

test("count_duration and count_ease shape the hero count-up only", () => {
  const counts = (params) => render(params, DATA).tl.calls.filter((c) => c.kind === "to" && "v" in c.vars);
  const dflt = counts(PARAMS);
  assert.strictEqual(dflt[0].vars.duration, 2.5);
  assert.strictEqual(dflt[0].vars.ease, "power1.out");
  const dramatic = counts({ ...PARAMS, count_duration: 4.5, count_ease: "expo.out" });
  assert.strictEqual(dramatic[0].vars.duration, 4.5);
  assert.strictEqual(dramatic[0].vars.ease, "expo.out");
  // the supporting figure keeps its own 1.0 s power1.out count-up
  assert.strictEqual(dramatic[1].vars.duration, 1.0);
  assert.strictEqual(dramatic[1].vars.ease, "power1.out");
});

test("invalid count settings fall back to the defaults", () => {
  const hero = (params) => render(params, DATA).tl.calls.find((c) => c.kind === "to" && "v" in c.vars).vars;
  const bad = hero({ ...PARAMS, count_duration: "slow", count_ease: 5 });
  assert.strictEqual(bad.duration, 2.5);
  assert.strictEqual(bad.ease, "power1.out");
  assert.strictEqual(hero({ ...PARAMS, count_duration: -1 }).duration, 2.5);
});

test("count_tail makes the last increments land as separate beats after the main count", () => {
  const round2 = (n) => Math.round(n * 100) / 100;
  const params = { ...PARAMS, heading: "H", count_duration: 3.0, count_ease: "expo.out", count_tail: [0.25, 0.35, 0.5, 0.7, 1.0] };
  const hero = render(params, DATA).tl.calls.filter((c) => c.kind === "to" && "v" in c.vars);
  // DATA has 1,240 commits: the main count stops 5 short, then five +1 beats
  const heroCalls = hero.filter((c) => [1235, 1236, 1237, 1238, 1239, 1240].includes(c.vars.v));
  assert.deepStrictEqual(heroCalls.map((c) => c.vars.v), [1235, 1236, 1237, 1238, 1239, 1240]);
  assert.strictEqual(round2(heroCalls[0].at), 1.0);                                      // heading delay 0.7 + 0.3
  assert.deepStrictEqual(heroCalls.slice(1).map((c) => round2(c.at)), [4.25, 4.6, 5.1, 5.8, 6.8]);
});

test("no count_tail, or an invalid one, keeps a single hero tween", () => {
  const heroTweens = (params) => render(params, DATA).tl.calls
    .filter((c) => c.kind === "to" && "v" in c.vars && c.vars.v >= 1200);
  assert.strictEqual(heroTweens(PARAMS).length, 1);
  assert.strictEqual(heroTweens({ ...PARAMS, count_tail: "slow" }).length, 1);
  assert.strictEqual(heroTweens({ ...PARAMS, count_tail: [] }).length, 1);
});

test("supporting figures never get tail beats", () => {
  const sub = render({ ...PARAMS, count_tail: [0.2, 0.3] }, DATA).tl.calls
    .filter((c) => c.kind === "to" && "v" in c.vars && c.vars.v <= 400);                 // merged_prs 310
  assert.strictEqual(sub.length, 1);
  assert.strictEqual(sub[0].vars.v, 310);
});

test("counter: odometer draws wheels instead of text and ends on the total", () => {
  const { tl, container } = render({ ...PARAMS, counter: "odometer" }, DATA);
  assert.strictEqual(find(container, "tw-odo-wheel").length, 4);                         // 1,240 has four digits
  finishCountUps(tl);
  const strips = find(container, "tw-odo-strip");
  assert.deepStrictEqual(
    strips.map((s) => Math.round(parseFloat(s.style.transform.match(/translateY\(-?([\d.]+)%/)[1]) * 11 / 100)),
    [1, 2, 4, 0]);
});

test("by default the hero stays a plain text count", () => {
  const { container } = render(PARAMS, DATA);
  assert.strictEqual(find(container, "tw-odo-wheel").length, 0);
  assert.strictEqual(find(container, "tw-hero-value")[0].textContent, "0");
  assert.strictEqual(find(render({ ...PARAMS, counter: "nonsense" }, DATA).container, "tw-odo-wheel").length, 0);
});
