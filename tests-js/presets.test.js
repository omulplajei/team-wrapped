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

test("impossible dates and months are returned unchanged; leap days work", () => {
  assert.strictEqual(presets.formatDate("2026-02-30"), "2026-02-30");
  assert.strictEqual(presets.formatDate("2026-13-01"), "2026-13-01");
  assert.strictEqual(presets.formatMonth("2026-00"), "2026-00");
  assert.strictEqual(presets.formatDate("2028-02-29", false), "29 February");
  assert.strictEqual(presets.formatDate("2026-02-29"), "2026-02-29");
});

test("formatDate never prints a comma", () => {
  const text = presets.formatDate("2026-03-14");
  assert.strictEqual(text, "Saturday 14 March");
  assert.ok(!text.includes(","));
});

test("fillTemplate treats prototype keys as missing and tolerates a null record", () => {
  assert.strictEqual(presets.fillTemplate("{constructor}|{toString}|{__proto__}|{hasOwnProperty}", {}), "|||");
  assert.strictEqual(presets.fillTemplate("{a}{b}", null), "");
  assert.strictEqual(presets.fillTemplate("{a}{b}", undefined), "");
});

test("date text does not depend on the process time zone", () => {
  const path = require("node:path");
  const { execFileSync } = require("node:child_process");
  const mod = path.join(__dirname, "..", "web", "presets", "presets.js");
  const script = `const p = require(${JSON.stringify(mod)}); console.log(p.formatDate('2026-03-14') + '|' + p.formatDate('2026-03-01', false));`;
  ["America/Los_Angeles", "Pacific/Auckland"].forEach((zone) => {
    const out = execFileSync(process.execPath, ["-e", script], { env: { ...process.env, TZ: zone } }).toString().trim();
    assert.strictEqual(out, "Saturday 14 March|1 March", zone);
  });
});

test("fillTemplate plural syntax prints the number and the singular or plural form", () => {
  const t = "with {merged_prs:pull request|pull requests} merged";
  assert.strictEqual(presets.fillTemplate(t, { merged_prs: 1 }), "with 1 pull request merged");
  assert.strictEqual(presets.fillTemplate(t, { merged_prs: 0 }), "with 0 pull requests merged");
  assert.strictEqual(presets.fillTemplate(t, { merged_prs: 12 }), "with 12 pull requests merged");
  assert.strictEqual(presets.fillTemplate(t, { merged_prs: 1500 }), "with 1,500 pull requests merged");
  assert.strictEqual(presets.fillTemplate("{merged_prs}", { merged_prs: 1 }), "1");
});

test("fillTemplate plural syntax prints nothing for a missing or non-number value", () => {
  const t = "[{n:day|days}]";
  assert.strictEqual(presets.fillTemplate(t, {}), "[]");
  assert.strictEqual(presets.fillTemplate(t, { n: null }), "[]");
  assert.strictEqual(presets.fillTemplate(t, { n: "1" }), "[]");
  assert.strictEqual(presets.fillTemplate(t, null), "[]");
});

test("fillTemplate plural syntax treats prototype keys as missing", () => {
  assert.strictEqual(presets.fillTemplate("{constructor:a|b}{__proto__:a|b}{toString:a|b}", {}), "");
});

test("scatterLayout gives every avatar its own spot inside the area, without overlap", () => {
  [[5, 900, 500], [60, 900, 500], [300, 900, 500], [1, 400, 300]].forEach(([count, w, h]) => {
    const { size, points } = presets.scatterLayout(count, w, h);
    assert.strictEqual(points.length, count);
    points.forEach((p) => {
      assert.ok(p.x - size / 2 >= -1e-9 && p.x + size / 2 <= w + 1e-9, `x in bounds for ${count}`);
      assert.ok(p.y - size / 2 >= -1e-9 && p.y + size / 2 <= h + 1e-9, `y in bounds for ${count}`);
    });
    for (let i = 0; i < count; i++) {
      for (let j = i + 1; j < count; j++) {
        assert.ok(Math.hypot(points[i].x - points[j].x, points[i].y - points[j].y) >= size - 1e-9, `${i} and ${j} overlap`);
      }
    }
  });
});

test("scatterLayout is deterministic, loose rather than a strict grid, and shrinks with the count", () => {
  const a = presets.scatterLayout(40, 900, 500);
  assert.deepStrictEqual(presets.scatterLayout(40, 900, 500), a);
  assert.ok(new Set(a.points.map((p) => Math.round(p.x * 10) / 10)).size > 10);
  assert.ok(presets.scatterLayout(5, 900, 500).size > a.size);
  assert.ok(a.size > presets.scatterLayout(300, 900, 500).size);
});

test("scatterLayout handles no avatars, and falls back to the minimum size when nothing fits", () => {
  assert.deepStrictEqual(presets.scatterLayout(0, 900, 500), { size: 0, points: [] });
  assert.strictEqual(presets.scatterLayout(5000, 300, 100).size, 20);
});

// The boxes a labelled layout draws: each avatar and the name label under it.
const labelledBoxes = ({ size, points, label }) => points.flatMap((p) => [
  { x0: p.x - size / 2, x1: p.x + size / 2, y0: p.y - size / 2, y1: p.y + size / 2 },
  { x0: p.x - label.width / 2, x1: p.x + label.width / 2, y0: p.y + label.offset, y1: p.y + label.offset + label.height },
]);
const overlaps = (a, b) => a.x0 < b.x1 - 1e-9 && b.x0 < a.x1 - 1e-9 && a.y0 < b.y1 - 1e-9 && b.y0 < a.y1 - 1e-9;

test("scatterLayout with labels reserves room so no avatar or label overlaps another, all inside the area", () => {
  [[900, 260], [1000, 520], [600, 400], [400, 300]].forEach(([w, h]) => {
    for (let count = 1; count <= 40; count++) {
      const layout = presets.scatterLayout(count, w, h, 120, 20, { labels: true });
      assert.strictEqual(layout.points.length, count);
      const boxes = labelledBoxes(layout);
      boxes.forEach((b) => assert.ok(b.x0 >= -1e-9 && b.x1 <= w + 1e-9 && b.y0 >= -1e-9 && b.y1 <= h + 1e-9,
        `inside ${w}x${h} for ${count}`));
      for (let i = 0; i < boxes.length; i++) {
        for (let j = i + 1; j < boxes.length; j++) {
          if (Math.floor(i / 2) === Math.floor(j / 2)) continue;     // an avatar and its own label
          assert.ok(!overlaps(boxes[i], boxes[j]), `boxes ${i} and ${j} overlap for ${count} in ${w}x${h}`);
        }
      }
    }
  });
});

test("scatterLayout labels sit under their avatar, are 1.6 avatars wide and scale with the avatar (min 9px)", () => {
  const big = presets.scatterLayout(2, 1000, 520, 120, 20, { labels: true });
  assert.ok(Math.abs(big.label.width - 1.6 * big.size) < 1e-9);
  assert.ok(big.label.offset >= big.size / 2);
  assert.ok(big.label.font > 9 && big.label.height > big.label.font);
  const small = presets.scatterLayout(40, 500, 200, 120, 20, { labels: true });
  assert.ok(small.size < big.size && small.label.font < big.label.font);
  assert.strictEqual(presets.scatterLayout(400, 300, 100, 120, 20, { labels: true }).label.font, 9);
  assert.deepStrictEqual(presets.scatterLayout(0, 900, 500, 120, 20, { labels: true }), { size: 0, points: [] });
});

test("scatterLayout without labels is unchanged and has no label metrics", () => {
  const plain = presets.scatterLayout(12, 900, 500);
  assert.deepStrictEqual(presets.scatterLayout(12, 900, 500, 120, 20, {}), plain);
  assert.strictEqual(plain.label, undefined);
});

test("wrapLines breaks after spaces and hyphens (not before a digit), and splits a word only when it cannot fit", () => {
  const measure = (text) => text.length * 10;      // 10px a character
  assert.deepStrictEqual(presets.wrapLines("sample-svc-1-prod", 1000, measure), ["sample-svc-1-prod"]);
  assert.deepStrictEqual(presets.wrapLines("sample-svc-1-prod", 120, measure), ["sample-", "svc-1-prod"]);
  assert.deepStrictEqual(presets.wrapLines("build bot", 60, measure), ["build", "bot"]);
  assert.deepStrictEqual(presets.wrapLines("abcdefghij", 40, measure), ["abcd", "efgh", "ij"]);
  assert.deepStrictEqual(presets.wrapLines("", 40, measure), [""]);
});

test("scatterLayout with names keeps one line when the names fit, as with plain labels", () => {
  const plain = presets.scatterLayout(3, 1000, 260, 120, 20, { labels: true });
  const named = presets.scatterLayout(3, 1000, 260, 120, 20, { labels: ["sample-bot", "helper-bot", "lint-bot"] });
  assert.deepStrictEqual(named.points, plain.points);
  assert.strictEqual(named.size, plain.size);
  assert.strictEqual(named.label.lines, 1);
  assert.strictEqual(named.label.width, plain.label.width);
});

test("scatterLayout with long names wraps them onto two lines so similar names stay readable", () => {
  const names = ["sample-svc-1-prod", "sample-svc-2-prod", "sample-svc-3-prod", "sample-very-long-automation-account-name"];
  [[800, 160], [375, 200], [1400, 120]].forEach(([w, h]) => {
    const layout = presets.scatterLayout(names.length, w, h, 120, 12, { labels: names });
    const { label } = layout;
    assert.ok(label.lines >= 1 && label.lines <= 2);
    assert.ok(Math.abs(label.height - label.lines * label.line) < 1e-9);
    names.forEach((name) => {
      const lines = presets.wrapLines(name, label.width, (t) => presets.estimateText(t, label.font));
      assert.ok(lines.length <= label.lines, `${name} fits in ${label.lines} line(s) at ${w}x${h}`);
    });
    const boxes = labelledBoxes(layout);
    for (let i = 0; i < boxes.length; i++) {
      const b = boxes[i];
      assert.ok(b.x0 >= -1e-9 && b.x1 <= w + 1e-9 && b.y0 >= -1e-9 && b.y1 <= h + 1e-9, `box ${i} inside ${w}x${h}`);
      for (let j = i + 1; j < boxes.length; j++) {
        if (Math.floor(i / 2) !== Math.floor(j / 2)) assert.ok(!overlaps(boxes[i], boxes[j]), `${i}/${j} at ${w}x${h}`);
      }
    }
  });
});

test("scatterLayout labels a name too long for two lines even at the smallest font across the whole width", () => {
  const layout = presets.scatterLayout(1, 100, 200, 120, 12, { labels: ["x".repeat(200)] });
  assert.strictEqual(layout.label.lines, 2);
  assert.ok(layout.label.width <= 100 + 1e-9);
});

// The cast scene with every stage on screen: humans, a heading band, then labelled robots.
const castBoxes = (layouts, bands) => layouts.flatMap((stage, i) => {
  const out = stage.points.map((p) => ({ kind: "avatar", stage: i,
    x0: p.x - stage.size / 2, x1: p.x + stage.size / 2, y0: p.y - stage.size / 2, y1: p.y + stage.size / 2 }));
  if (stage.label) {
    const l = stage.label;
    stage.points.forEach((p) => out.push({ kind: "label", stage: i,
      x0: p.x - l.width / 2, x1: p.x + l.width / 2, y0: p.y + l.offset, y1: p.y + l.offset + l.height }));
  }
  if (i > 0) out.push({ kind: "band", stage: i, x0: 0, x1: Infinity, y0: stage.bandTop, y1: stage.bandTop + bands[i] });
  return out;
});
const robotNames = (n) => Array.from({ length: n }, (_, i) =>
  [`sample-svc-${i}-prod`, "sample-release-helper", "sample-dependency-updater", "qa", `sample-very-long-automation-name-${i}`][i % 5]);

test("castLayout fits humans, the robot heading band and labelled robots on any stage without overlap", () => {
  const BAND = 48;
  [[1440, 800], [1024, 700], [800, 1000], [375, 700]].forEach(([w, h]) => {
    [5, 40, 150, 331, 600].forEach((humans) => {
      [0, 1, 3, 11, 25].forEach((robots) => {
        const stages = [{ count: humans }].concat(robots > 0 ? [{ count: robots, names: robotNames(robots) }] : []);
        const bands = [0, BAND];
        const layouts = presets.castLayout(w, h, stages, { bands });
        const where = `${humans} humans + ${robots} robots in ${w}x${h}`;
        assert.strictEqual(layouts.length, stages.length);
        layouts.forEach((l, i) => {
          assert.strictEqual(l.points.length, stages[i].count);
          assert.ok(l.size >= 12, `avatars at least 12px for ${where}`);
        });
        const boxes = castBoxes(layouts, bands);
        boxes.forEach((b) => assert.ok(b.x0 >= -1e-9 && Math.min(b.x1, w) <= w + 1e-9 && b.y0 >= -1e-9 && b.y1 <= h + 1e-9,
          `${b.kind} of stage ${b.stage} inside for ${where}`));
        for (let i = 0; i < boxes.length; i++) {
          for (let j = i + 1; j < boxes.length; j++) {
            const a = boxes[i];
            const b = boxes[j];
            if (a.kind === "band" && b.kind === "band") continue;
            assert.ok(!overlaps(a, b), `${a.kind} ${i} and ${b.kind} ${j} overlap for ${where}`);
          }
        }
        if (robots > 0) {
          const { label } = layouts[1];
          robotNames(robots).forEach((name) => {
            const lines = presets.wrapLines(name, label.width, (t) => presets.estimateText(t, label.font));
            assert.ok(lines.length <= label.lines, `${name} readable for ${where}`);
          });
        }
      });
    });
  });
});

test("castLayout keeps the familiar split for a small team: humans above, robots below, avatars as large as before", () => {
  const stages = [{ count: 10 }, { count: 3, names: ["sample-bot", "helper-bot", "lint-bot"] }];
  const [humans, bots] = presets.castLayout(1000, 520, stages, { bands: [0, 48] });
  // the space is shared by headcount, with a quarter of the team as the floor for each stage
  const before = presets.scatterLayout(10, 1000, (472 * 10) / (10 + 13 * 0.25), 120, 20);
  assert.strictEqual(humans.size, before.size);
  assert.deepStrictEqual(humans.points, before.points);
  assert.ok(bots.bandTop >= Math.max(...humans.points.map((p) => p.y + humans.size / 2)) - 1e-9);
  assert.strictEqual(bots.label.lines, 1);
  assert.deepStrictEqual(presets.castLayout(1000, 520, [{ count: 0 }], { bands: [0] })[0].points, []);
});

test("castLayout gives a taller heading band its full height", () => {
  const stages = [{ count: 331 }, { count: 11, names: robotNames(11) }];
  const [humans, bots] = presets.castLayout(800, 1000, stages, { bands: [0, 96] });
  assert.ok(Math.max(...humans.points.map((p) => p.y + humans.size / 2)) <= bots.bandTop + 1e-9);
  assert.ok(Math.min(...bots.points.map((p) => p.y - bots.size / 2)) >= bots.bandTop + 96 - 1e-9);
});

test("dropIn drops targets from above, then squashes and springs them back on landing", () => {
  const calls = [];
  const tl = {
    fromTo: (t, from, vars, at) => { calls.push({ kind: "fromTo", from, vars, at }); return tl; },
    to: (t, vars, at) => { calls.push({ kind: "to", vars, at }); return tl; },
  };
  assert.strictEqual(presets.dropIn(tl, ["a", "b"], 1, 0.1, (i) => 300 + i, 1), tl);
  const [drop, squash, spring] = calls;
  assert.strictEqual(drop.from.y(1), -301);
  assert.strictEqual(drop.vars.ease, "bounce.out");
  assert.strictEqual(drop.vars.stagger, 0.1);
  assert.ok(squash.vars.scaleY < 1 && squash.vars.scaleX > 1);
  assert.ok(squash.at > 1 && squash.at < 2);
  assert.deepStrictEqual([spring.vars.scaleX, spring.vars.scaleY], [1, 1]);
  assert.ok(spring.at > squash.at);
});
