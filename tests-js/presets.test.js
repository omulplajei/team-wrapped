const test = require("node:test");
const assert = require("node:assert");
const presets = require("../web/presets/presets.js");
const { makeEl } = require("./helpers.js");

test("format uses thousands separators", () => {
  assert.strictEqual(presets.format(1240), "1,240");
  assert.strictEqual(presets.format(48200), "48,200");
  assert.strictEqual(presets.format(0), "0");
  assert.strictEqual(presets.format(-5), "-5");
});

test("lookup resolves family.name datasets and single-name datasets", () => {
  const data = { "summary.totals": { commits: 5 }, contributors: { total: 2, by_kind: { bot: 1 } } };
  assert.strictEqual(presets.lookup(data, "summary.totals.commits"), 5);
  assert.strictEqual(presets.lookup(data, "contributors.total"), 2);
  assert.strictEqual(presets.lookup(data, "contributors.by_kind.bot"), 1);
  assert.strictEqual(presets.lookup(data, "summary.totals.nope"), undefined);
  assert.strictEqual(presets.lookup(data, "other.thing.value"), undefined);
});

test("isPartial matches the dataset a reference points to", () => {
  const partial = ["delivery_volume.lines"];
  assert.strictEqual(presets.isPartial(partial, "delivery_volume.lines.total_net"), true);
  assert.strictEqual(presets.isPartial(partial, "summary.totals.commits"), false);
  assert.strictEqual(presets.isPartial([], "summary.totals.commits"), false);
});

test("animation presets add tweens to the timeline and return it", () => {
  const calls = [];
  const tl = {
    from: (t, v, at) => { calls.push(["from", v, at]); return tl; },
    to: (t, v, at) => { calls.push(["to", v, at]); return tl; },
  };
  assert.strictEqual(presets.fadeIn(tl, {}, 1, 0.5), tl);
  assert.strictEqual(presets.stagger(tl, [], 2), tl);
  assert.strictEqual(presets.popIn(tl, [], 3), tl);
  const el = { textContent: "" };
  assert.strictEqual(presets.countUp(tl, el, 100, 4, 1), tl);
  assert.strictEqual(el.textContent, "0");      // starts at zero
  assert.deepStrictEqual(calls.map((c) => c[0]), ["from", "from", "from", "to"]);
  assert.deepStrictEqual(calls.map((c) => c[2]), [1, 2, 3, 4]);
  // the count-up callback writes formatted numbers
  const to = calls[3][1];
  assert.strictEqual(to.v, 100);
});

test("bubbleIn adds one staggered from-tween with deterministic offsets and returns the timeline", () => {
  const calls = [];
  const tl = { from: (t, v, at) => { calls.push({ t, v, at }); return tl; } };
  assert.strictEqual(presets.bubbleIn(tl, [{}, {}, {}], 0.6, 0.1), tl);
  assert.strictEqual(calls.length, 1);
  const { v, at } = calls[0];
  assert.strictEqual(at, 0.6);
  assert.strictEqual(v.stagger, 0.1);
  assert.strictEqual(v.opacity, 0);
  assert.ok(v.scale > 0 && v.scale < 1);
  assert.ok(/^elastic/.test(v.ease));
  // offsets are functions of the target index, so scrubbing and replaying never changes the layout
  assert.strictEqual(typeof v.y, "function");
  assert.strictEqual(typeof v.x, "function");
  assert.strictEqual(v.y(3), v.y(3));
  assert.ok(v.y(0) > 0);                     // bubbles rise from below
  assert.notStrictEqual(v.x(1), v.x(2));     // and come from different sides
});

function neededHeight(count, size, width) {
  const gapX = size * 0.14, gapY = size * 0.2;
  const cols = Math.max(1, Math.floor((width + gapX) / (size + gapX)));
  const rows = Math.ceil(count / cols);
  return rows * (size * 0.75) + (rows - 1) * gapY;
}

test("fitFolderSize gives the largest size when there is plenty of room", () => {
  assert.strictEqual(presets.fitFolderSize(3, 1120, 600).size, 128);
});

test("fitFolderSize fits many repositories into the given area", () => {
  const big = presets.fitFolderSize(45, 1120, 574);
  assert.ok(big.size >= 36);
  assert.ok(neededHeight(45, big.size, 1120) <= 574);
  const phone = presets.fitFolderSize(14, 311, 614);
  assert.ok(neededHeight(14, phone.size, 311) <= 614);
});

test("fitFolderSize never grows with more repositories", () => {
  const sizes = [10, 40, 150].map((n) => presets.fitFolderSize(n, 1120, 574).size);
  assert.ok(sizes[0] >= sizes[1] && sizes[1] >= sizes[2]);
});

test("fitFolderSize falls back to the minimum and keeps the font readable", () => {
  assert.deepStrictEqual(presets.fitFolderSize(500, 300, 300), { size: 36, font: 5 });
  for (const n of [1, 40, 500]) assert.ok(presets.fitFolderSize(n, 600, 400).font >= 5);
});

test("fitFolderSize returns exact expected values for small and large repo counts", () => {
  // 3 repos with ample space: 900 width, 492 height
  // size 128: gapX=17.92, gapY=25.6, cols=6, rows=1, needed=96 <= 492 (fits)
  // font = max(5, round(12.8*10)/10) = 12.8
  assert.deepStrictEqual(presets.fitFolderSize(3, 900, 492), { size: 128, font: 12.8 });
});

test("fitFolderSize for 45 repos is the largest size that fits the constraint", () => {
  // 45 repos with 1120 width, 574 height
  // size 110 fits: cols=9, rows=5, needed=500.5 <= 574
  // size 112 does not: cols=8, rows=6, needed=616 > 574
  const result = presets.fitFolderSize(45, 1120, 574);
  assert.strictEqual(result.size, 110);

  // Verify that size+2 (112) would exceed the height constraint
  const gapX = 112 * 0.14;
  const gapY = 112 * 0.2;
  const cols = Math.max(1, Math.floor((1120 + gapX) / (112 + gapX)));
  const rows = Math.ceil(45 / cols);
  const needed = rows * (112 * 0.75) + (rows - 1) * gapY;
  assert.ok(needed > 574, `size 112 needs ${needed}px, exceeds 574px`);
});

test("swellIn appears, grows past its size and settles back to 1", () => {
  const calls = [];
  const tl = {
    fromTo: (t, from, vars, at) => { calls.push({ kind: "fromTo", from, vars, at }); return tl; },
    to: (t, vars, at) => { calls.push({ kind: "to", vars, at }); return tl; },
  };
  assert.strictEqual(presets.swellIn(tl, {}, 2, 1.25, 0.6), tl);
  assert.strictEqual(calls.length, 2);
  const [grow, settle] = calls;
  assert.deepStrictEqual(grow.from, { opacity: 0, scale: 0 });
  assert.strictEqual(grow.vars.opacity, 1);
  assert.strictEqual(grow.vars.scale, 1.25);
  assert.strictEqual(grow.at, 2);
  assert.strictEqual(settle.vars.scale, 1);
  assert.ok(Math.abs(settle.at - (2 + 0.6 * 0.55)) < 1e-9);
  assert.ok(Math.abs(grow.vars.duration + settle.vars.duration - 0.6) < 1e-9);
});

test("countUp takes an optional ease and keeps power1.out by default", () => {
  const calls = [];
  const tl = { to: (target, vars, at) => { calls.push({ vars, at }); return tl; } };
  presets.countUp(tl, { textContent: "" }, 10, 0, 1);
  presets.countUp(tl, { textContent: "" }, 10, 0, 1, "expo.out");
  assert.strictEqual(calls[0].vars.ease, "power1.out");
  assert.strictEqual(calls[1].vars.ease, "expo.out");
});

function countCalls(to, at, duration, tail) {
  const calls = [];
  const state = { text: "" };
  const el = { textContent: "" };
  const tl = { to: (target, vars, when) => { calls.push({ target, vars, at: when }); return tl; } };
  presets.countUp(tl, el, to, at, duration, "expo.out", tail);
  const run = () => calls.forEach((c) => { c.target.v = c.vars.v; c.vars.onUpdate(); });
  return { calls, el, run };
}
const r2 = (n) => Math.round(n * 100) / 100;

test("without a tail countUp makes one tween to the total, as before", () => {
  const { calls } = countCalls(10, 1, 2, undefined);
  assert.strictEqual(calls.length, 1);
  assert.strictEqual(calls[0].vars.v, 10);
  assert.strictEqual(calls[0].vars.ease, "expo.out");
});

test("a tail counts fast to total minus the beats, then adds one per beat after each pause", () => {
  const { calls, el, run } = countCalls(10, 1, 3, [0.25, 0.5, 1.0]);
  assert.deepStrictEqual(calls.map((c) => c.vars.v), [7, 8, 9, 10]);
  assert.strictEqual(calls[0].vars.duration, 3);
  assert.strictEqual(calls[0].at, 1);
  assert.deepStrictEqual(calls.slice(1).map((c) => r2(c.at)), [4.25, 4.75, 5.75]);      // 1 + 3, then + the pauses
  assert.ok(calls.slice(1).every((c) => c.vars.duration <= 0.05 && c.vars.ease === "none"));
  run();
  assert.strictEqual(el.textContent, "10");                                              // exact total at the end
});

test("invalid tail entries are ignored and the beats never exceed the total", () => {
  const { calls } = countCalls(10, 0, 1, [0, -1, "x", NaN, Infinity, 0.5]);
  assert.deepStrictEqual(calls.map((c) => c.vars.v), [9, 10]);                           // only 0.5 is valid
  const small = countCalls(2, 0, 1, [1, 1, 1]);
  assert.deepStrictEqual(small.calls.map((c) => c.vars.v), [0, 1, 2]);                  // capped at the total
  assert.deepStrictEqual(countCalls(10, 0, 1, "slow").calls.map((c) => c.vars.v), [10]);
});

test("a beat is never longer than the pause before it, so beats cannot overlap", () => {
  const { calls } = countCalls(10, 0, 1, [0.01, 0.5]);
  const beats = calls.slice(1);
  assert.deepStrictEqual(beats.map((c) => c.vars.duration), [0.01, 0.05]);
  beats.forEach((c, i) => {
    if (i > 0) assert.ok(c.at >= beats[i - 1].at + beats[i - 1].vars.duration - 1e-9);
  });
});

test("wheelPositions: the units wheel turns continuously, others turn only as a carry", () => {
  assert.deepStrictEqual(presets.wheelPositions(0, 4), [0, 0, 0, 0]);
  assert.deepStrictEqual(presets.wheelPositions(1239.5, 4), [9.5, 3.5, 2, 1]);
  assert.deepStrictEqual(presets.wheelPositions(1240, 4), [0, 4, 2, 1]);
  assert.deepStrictEqual(presets.wheelPositions(1990, 4), [0, 9, 9, 1]);
  assert.deepStrictEqual(presets.wheelPositions(1999.5, 4), [9.5, 9.5, 9.5, 1.5]);   // the carry cascades up
  assert.deepStrictEqual(presets.wheelPositions(2000, 4), [0, 0, 0, 2]);
});

function odometerCalls(to, tail) {
  const calls = [];
  const tl = { to: (target, vars, when) => { calls.push({ target, vars, at: when }); return tl; } };
  const el = makeEl("div");
  presets.odometer(tl, el, to, 1, 3, "expo.out", tail, { createElement: makeEl });
  const run = (upTo = calls.length) => calls.slice(0, upTo).forEach((c) => { c.target.v = c.vars.v; c.vars.onUpdate(); });
  return { el, calls, run };
}
const collect = (el, className, found = []) => {
  if (el.className === className) found.push(el);
  (el.children || []).forEach((kid) => collect(kid, className, found));
  return found;
};

test("odometer builds one wheel per digit with a separator between thousands and hundreds", () => {
  const { el } = odometerCalls(1240, []);
  assert.strictEqual(el.children.length, 1);
  assert.strictEqual(el.children[0].className, "tw-odo");
  assert.strictEqual(collect(el, "tw-odo-wheel").length, 4);
  const seps = collect(el, "tw-odo-sep");
  assert.deepStrictEqual(seps.map((s) => s.textContent), [","]);
  const cells = collect(collect(el, "tw-odo-strip")[0], "tw-odo-digit").map((c) => c.textContent);
  assert.deepStrictEqual(cells, ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]);
  // order: thousands wheel, separator, then hundreds, tens, units
  assert.deepStrictEqual(el.children[0].children.map((c) => c.className),
    ["tw-odo-wheel", "tw-odo-sep", "tw-odo-wheel", "tw-odo-wheel", "tw-odo-wheel"]);
});

test("the wheels end on the exact total and leading zero wheels start dimmed", () => {
  const { el, run } = odometerCalls(1240, []);
  const strips = collect(el, "tw-odo-strip");            // most significant first: 1, 2, 4, 0
  const wheels = collect(el, "tw-odo-wheel");
  assert.deepStrictEqual(wheels.map((w) => w.style.opacity), ["0.3", "0.3", "0.3", "1"]);   // at 0 only the units wheel is lit
  run();
  assert.deepStrictEqual(strips.map((s) => Math.round(parseFloat(s.style.transform.match(/translateY\(-?([\d.]+)%/)[1]) * 11 / 100)), [1, 2, 4, 0]);
  assert.deepStrictEqual(wheels.map((w) => w.style.opacity), ["1", "1", "1", "1"]);
});

test("odometer uses the same count schedule as countUp, with rolling beats", () => {
  const { calls } = odometerCalls(1240, [0.25, 0.35, 0.5]);
  assert.deepStrictEqual(calls.map((c) => c.vars.v), [1237, 1238, 1239, 1240]);
  assert.strictEqual(calls[0].vars.ease, "expo.out");
  const beats = calls.slice(1);
  assert.deepStrictEqual(beats.map((c) => r2(c.at)), [4.25, 4.6, 5.1]);
  assert.deepStrictEqual(beats.map((c) => c.vars.duration), [0.25, 0.3, 0.3]);          // min(0.3, pause)
  assert.ok(beats.every((c) => c.vars.ease === "power2.inOut"));
});

const stripDigit = (s) => Math.round(parseFloat(s.style.transform.match(/translateY\(-?([\d.]+)%/)[1]) * 11 / 100);
const stripPos = (s) => parseFloat(s.style.transform.match(/translateY\(-?([\d.]+)%/)[1]) * 11 / 100;

test("odometer rounds a non-integer total so the wheels end exactly", () => {
  const { el, calls, run } = odometerCalls(12.5, []);
  run();
  assert.deepStrictEqual(collect(el, "tw-odo-strip").map(stripDigit), [1, 3]);
  assert.strictEqual(el.attributes["aria-label"], "13");
  assert.strictEqual(calls[0].vars.v, 13);
});

test("odometer survives NaN, negative and zero totals with a single wheel at 0", () => {
  for (const bad of [NaN, -5, 0]) {
    const { el, run } = odometerCalls(bad, []);
    run();
    const wheels = collect(el, "tw-odo-wheel");
    assert.strictEqual(wheels.length, 1);
    assert.strictEqual(stripPos(collect(el, "tw-odo-strip")[0]), 0);
  }
});

test("odometer clamps overshooting tween values to 0 and the total", () => {
  const { el, calls } = odometerCalls(1240, []);
  const strips = collect(el, "tw-odo-strip");
  calls[0].target.v = -50; calls[0].vars.onUpdate();
  assert.deepStrictEqual(strips.map(stripPos), [0, 0, 0, 0]);
  calls[0].target.v = 999999; calls[0].vars.onUpdate();
  assert.deepStrictEqual(strips.map(stripDigit), [1, 2, 4, 0]);
});

test("odometer exposes an image role with the formatted label and hides the wheels", () => {
  const { el } = odometerCalls(1240, []);
  assert.strictEqual(el.attributes.role, "img");
  assert.strictEqual(el.attributes["aria-label"], "1,240");
  assert.strictEqual(el.children[0].attributes["aria-hidden"], "true");
});

test("odometer lays out seven digits with two separators", () => {
  const { el } = odometerCalls(1234567, []);
  assert.strictEqual(collect(el, "tw-odo-wheel").length, 7);
  assert.strictEqual(collect(el, "tw-odo-sep").length, 2);
  assert.deepStrictEqual(el.children[0].children.map((c) => c.className),
    ["tw-odo-wheel", "tw-odo-sep", "tw-odo-wheel", "tw-odo-wheel", "tw-odo-wheel", "tw-odo-sep", "tw-odo-wheel", "tw-odo-wheel", "tw-odo-wheel"]);
});

test("odometer scrubbing backward returns every wheel to rest and re-dims", () => {
  const { el, calls, run } = odometerCalls(1240, []);
  run();
  calls[0].target.v = 0; calls[0].vars.onUpdate();
  assert.deepStrictEqual(collect(el, "tw-odo-strip").map(stripPos), [0, 0, 0, 0]);
  assert.deepStrictEqual(collect(el, "tw-odo-wheel").map((w) => w.style.opacity), ["0.3", "0.3", "0.3", "1"]);
});

test("odometer lights a wheel as soon as it starts rolling", () => {
  const { el, calls } = odometerCalls(100, []);
  const wheels = collect(el, "tw-odo-wheel");
  calls[0].target.v = 9.5; calls[0].vars.onUpdate();
  assert.strictEqual(wheels[1].style.opacity, "1");
  assert.strictEqual(wheels[0].style.opacity, "0.3");
  calls[0].target.v = 5; calls[0].vars.onUpdate();
  assert.strictEqual(wheels[1].style.opacity, "0.3");
});

test("formatDate and formatMonth read ISO values in UTC, in English", () => {
  assert.strictEqual(presets.formatDate("2026-03-14"), "Saturday 14 March");
  assert.strictEqual(presets.formatDate("2026-03-14", false), "14 March");
  assert.strictEqual(presets.formatDate("2026-12-31", false), "31 December");
  assert.strictEqual(presets.formatMonth("2026-03"), "March");
  assert.strictEqual(presets.formatMonth("2026-12"), "December");
  assert.strictEqual(presets.formatDate("tomorrow"), "tomorrow");        // not an ISO date: unchanged
  assert.strictEqual(presets.formatMonth("2026-13"), "2026-13");          // impossible month: unchanged
});

test("fillTemplate fills record fields with the right formats", () => {
  const record = { value: 1234, repo: "sample-api", pr_number: 4821, date: "2026-03-14", from: "2026-03-02", to: "2026-03-20", month: "2026-03", merged_prs: 1500 };
  assert.strictEqual(presets.fillTemplate("in {repo}, pull request #{pr_number}", record), "in sample-api, pull request #4821");
  assert.strictEqual(presets.fillTemplate("on {date}", record), "on Saturday 14 March");
  assert.strictEqual(presets.fillTemplate("from {from} to {to}", record), "from 2 March to 20 March");
  assert.strictEqual(presets.fillTemplate("in {month}, {merged_prs} merged", record), "in March, 1,500 merged");
  assert.strictEqual(presets.fillTemplate("{value} things", record), "1,234 things");
  assert.strictEqual(presets.fillTemplate("{missing}|{repo}", record), "|sample-api");   // unknown fields become empty
  assert.strictEqual(presets.fillTemplate("no placeholders", record), "no placeholders");
});
