const test = require("node:test");
const assert = require("node:assert");
const presets = require("../web/presets/presets.js");
const { makeEl, loadRenderer, fakeTimeline, find } = require("./helpers.js");

const flow = loadRenderer("capability-flow");
const { HEX_H, HEX_AREA, FILL, MIN_SIDE, MAX_SIDE } = flow.constants;
const SQRT3 = Math.sqrt(3);

const group = (name, category, commits, label) => ({ name, label: label || name, category, total: commits.length, commits });
const GROUPS = [
  group("alpha", "core", [[0, 10], [0, 400], [40, 30], [200, 5000], [364, 0]], "Core Alpha"),
  group("beta", "extension", [[3, 20], [100, 60]]),
  group("eta", undefined, []),
];
const dataFor = (groups, window = { days: 365, start: "2026-01-01" }) => ({
  "commit_flow.groups": groups, "commit_flow.window": window,
});
const PARAMS = { heading: "Every commit, one block", groups: "commit_flow.groups", window: "commit_flow.window" };

function render(params = PARAMS, data = dataFor(GROUPS), partial = [], duration = 30) {
  const tl = fakeTimeline();
  const container = makeEl("section");
  const result = loadRenderer("capability-flow").render({
    container, data, params, partial, duration, gsap: { timeline: () => tl }, presets,
  });
  return { tl, container, result };
}

// The one tween that drives the scene: seek it to a scene time.
function seek(tl, time) {
  const call = tl.calls.find((c) => c.kind === "to" && c.vars.onUpdate && "t" in c.target);
  call.target.t = time / call.vars.duration;
  call.vars.onUpdate();
  return call;
}

// ---- honeycomb layout -------------------------------------------------

function hexInside(c, r, w, h) {
  const eps = 1e-6;
  return c.x - r >= -eps && c.x + r <= w + eps && c.y - (r * SQRT3) / 2 >= -eps && c.y + (r * SQRT3) / 2 <= h + eps;
}

test("honeycomb: 1 to 14 hexagons fit inside the area without overlapping", () => {
  for (const [w, h] of [[1200, 560], [360, 520], [800, 800]]) {
    for (let n = 1; n <= 14; n++) {
      const out = flow.honeycombLayout(n, w, h);
      assert.strictEqual(out.centres.length, n);
      assert.ok(out.radius > 0 && out.radius < out.cell, `n=${n}`);
      out.centres.forEach((c) => assert.ok(hexInside(c, out.radius, w, h), `n=${n} ${w}x${h} ${JSON.stringify(c)}`));
      for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
          const d = Math.hypot(out.centres[i].x - out.centres[j].x, out.centres[i].y - out.centres[j].y);
          assert.ok(d >= SQRT3 * out.cell - 1e-6, `n=${n} cells ${i} and ${j} overlap`);
        }
      }
    }
  }
});

test("honeycomb: the first item in the order gets the most central cell", () => {
  const w = 1200;
  const h = 560;
  const out = flow.honeycombLayout(7, w, h, [6, 5, 4, 3, 2, 1, 0]);
  const off = (c) => Math.hypot(c.x - w / 2, c.y - h / 2);
  const dists = out.centres.map(off);
  assert.ok(dists[6] <= Math.min(...dists) + 1e-6);
});

test("honeycomb: a wide area gets several columns, a tall narrow one fewer", () => {
  const cols = (out) => new Set(out.centres.map((c) => Math.round(c.x))).size;
  assert.ok(cols(flow.honeycombLayout(7, 1400, 500)) >= 4);
  assert.ok(cols(flow.honeycombLayout(7, 340, 520)) <= 3);
});

test("honeycomb: the radius respects the cap and empty input gives no cells", () => {
  assert.ok(flow.honeycombLayout(1, 2000, 2000, undefined, 200).cell <= 200);
  assert.deepStrictEqual(flow.honeycombLayout(0, 100, 100).centres, []);
  assert.deepStrictEqual(flow.honeycombLayout(3, 0, 100).centres, []);
});

// ---- layout override -----------------------------------------------

test("override: a complete, non-overlapping layout is used and centred", () => {
  const out = flow.overrideLayout(["a", "b", "c"], [
    { group: "a", col: 0, row: 0 }, { group: "b", col: 1, row: 0.5 }, { group: "c", col: 0, row: 1 },
  ], 1000, 600);
  assert.ok(out);
  assert.strictEqual(out.centres.length, 3);
  out.centres.forEach((c) => assert.ok(hexInside(c, out.radius, 1000, 600)));
  assert.ok(Math.abs(out.centres[0].x - out.centres[2].x) < 1e-6);
  assert.ok(out.centres[1].x > out.centres[0].x);
});

test("override: bad entries are ignored and an incomplete or overlapping layout is refused", () => {
  const names = ["a", "b"];
  assert.strictEqual(flow.overrideLayout(names, "nope", 100, 100), null);
  assert.strictEqual(flow.overrideLayout(names, [{ group: "a", col: 0, row: 0 }], 100, 100), null);
  assert.strictEqual(flow.overrideLayout(names, [{ group: "a", col: 0, row: 0 }, { group: "b", col: 0, row: 0 }], 100, 100), null);
  assert.strictEqual(flow.overrideLayout(names, [{ group: "a", col: 0, row: 0 }, { group: "b", col: 1.5, row: 2 }], 100, 100), null);
  assert.strictEqual(flow.overrideLayout(names, [{ group: "a", col: 0, row: 0 }, { group: "b", col: 0, row: 0.3 }], 100, 100), null);
  const ok = flow.overrideLayout(names, [null, 3, { group: "zz", col: 9, row: 9 }, { group: "a", col: 0, row: 0 },
    { group: "a", col: 5, row: 5 }, { group: "b", col: 0, row: 1 }], 100, 100);
  assert.ok(ok);
  assert.ok(ok.centres[1].y > ok.centres[0].y);
});

// ---- block sizes --------------------------------------------------------

test("blocks: side grows with the square root of lines, clamped to the min and max", () => {
  assert.strictEqual(flow.blockSide(0.01, 0), MIN_SIDE);
  assert.strictEqual(flow.blockSide(0.01, 1e9), MAX_SIDE);
  assert.ok(Math.abs(flow.blockSide(0.01, 100) - 0.1) < 1e-12);
  assert.ok(MAX_SIDE < 0.35);
});

test("blocks: one shared scale makes the busiest group fill half the hexagon", () => {
  const busy = Array.from({ length: 400 }, (_, i) => (i * 37) % 300);
  const quiet = [10, 20, 30];
  const k = flow.blockScale([busy, quiet]);
  const area = (lines) => lines.reduce((sum, l) => sum + flow.blockSide(k, l) ** 2, 0);
  assert.ok(Math.abs(area(busy) - FILL * HEX_AREA) < 1e-3);
  assert.ok(area(quiet) < area(busy) / 10);
});

test("blocks: too many commits fall back to the minimum size, too few to slabs", () => {
  assert.strictEqual(flow.blockScale([new Array(100000).fill(5)]), 0);
  assert.ok(flow.blockSide(flow.blockScale([[1]]), 1) === MAX_SIDE);
});

// ---- packing ------------------------------------------------------------

function assertInsideHex(xs, ys, sides) {
  for (let i = 0; i < sides.length; i++) {
    const s = sides[i];
    const y0 = ys[i];
    const y1 = ys[i] + s;
    assert.ok(y0 >= 0 && y1 <= HEX_H + 1e-6, `block ${i} out vertically`);
    for (const y of [y0, y1]) {
      const hw = flow.hexHalfWidth(Math.min(y, HEX_H));
      assert.ok(xs[i] >= 0.5 - hw - 1e-6 && xs[i] + s <= 0.5 + hw + 1e-6, `block ${i} out sideways at ${y}`);
    }
  }
}

test("packing: every block stays inside the hexagon, even when the pile overflows", () => {
  for (const n of [1, 50, 2000]) {
    const sides = Float32Array.from({ length: n }, (_, i) => [0.006, 0.02, 0.05, 0.33][i % 4]);
    const { x, y } = flow.packGroup(sides, 3);
    assertInsideHex(x, y, sides);
  }
});

test("packing: blocks that are not squeezed at the top do not overlap", () => {
  const sides = Float32Array.from({ length: 120 }, (_, i) => 0.01 + ((i * 13) % 7) * 0.01);
  const { x, y } = flow.packGroup(sides, 1);
  for (let i = 0; i < sides.length; i++) {
    for (let j = i + 1; j < sides.length; j++) {
      const overlapX = Math.min(x[i] + sides[i], x[j] + sides[j]) - Math.max(x[i], x[j]);
      const overlapY = Math.min(y[i] + sides[i], y[j] + sides[j]) - Math.max(y[i], y[j]);
      assert.ok(overlapX <= 1 / 240 + 1e-6 || overlapY <= 1e-5, `blocks ${i} and ${j} overlap`);
    }
  }
});

test("packing is deterministic and depends on the group index", () => {
  const sides = Float32Array.from({ length: 60 }, () => 0.03);
  const a = flow.packGroup(sides, 0);
  const b = flow.packGroup(sides, 0);
  const c = flow.packGroup(sides, 1);
  assert.deepStrictEqual(Array.from(a.x), Array.from(b.x));
  assert.deepStrictEqual(Array.from(a.y), Array.from(b.y));
  assert.notDeepStrictEqual(Array.from(a.x), Array.from(c.x));
});

// ---- timing ---------------------------------------------------------------

test("timing: a lead-in and a hold around the year", () => {
  assert.deepStrictEqual(flow.timingPlan(30), { lead: 2.5, hold: 4, play: 23.5, duration: 30 });
  const short = flow.timingPlan(10);
  assert.ok(short.lead < 2.5 && short.hold < 4 && Math.abs(short.lead + short.hold + short.play - 10) < 1e-9);
});

test("prepare: landing times follow the day, sorted, inside the play time", () => {
  const model = flow.prepare(GROUPS, { days: 365, start: "2026-01-01" }, 30);
  const alpha = model.groups[0];
  assert.strictEqual(alpha.n, 5);
  for (let i = 1; i < alpha.n; i++) assert.ok(alpha.land[i] >= alpha.land[i - 1]);
  assert.ok(alpha.land[0] > 2.5 && alpha.land[0] < 2.6);
  assert.ok(alpha.land[4] <= 2.5 + 23.5 && alpha.land[4] > 25.9);
  assert.ok(Math.abs(alpha.land[3] - (2.5 + (200.5 / 365) * 23.5)) < 1e-9);
  assert.strictEqual(model.groups[2].n, 0);
  // the biggest commits (at least 3) are flagged for a flash
  assert.deepStrictEqual(alpha.big, [1, 3]);
  assert.deepStrictEqual(model.groups[1].big, [1]);
});

test("prepare: unsorted or malformed commits are cleaned and ordered", () => {
  const model = flow.prepare([group("x", "core", [[50, 1], "bad", [10, -5], [400, 3], [null, 2]])], { days: 365 }, 30);
  assert.strictEqual(model.groups[0].n, 3);
  const land = Array.from(model.groups[0].land);
  assert.deepStrictEqual(land, [...land].sort((a, b) => a - b));
  assert.ok(land[2] <= 26.0 + 1e-9);
});

test("fall: starts above, ends on the pile, and bounces a little in between", () => {
  assert.strictEqual(flow.fallY(0, 0.8, 0.1, 0.05), 0.8);
  assert.strictEqual(flow.fallY(1, 0.8, 0.1, 0.05), 0.1);
  assert.ok(flow.fallY(0.85, 0.8, 0.1, 0.05) > 0.1);
  assert.ok(flow.fallY(0.4, 0.8, 0.1, 0.05) < 0.8);
});

test("month segments cover the window with short labels", () => {
  const segs = flow.monthSegments("2026-01-01", 365, presets.formatMonth);
  assert.strictEqual(segs.length, 12);
  assert.deepStrictEqual(segs.map((s) => s.label), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]);
  assert.deepStrictEqual([segs[0].from, segs[0].to, segs[1].to, segs[11].to], [0, 31, 59, 365]);
  const mid = flow.monthSegments("2026-03-15", 30, presets.formatMonth);
  assert.deepStrictEqual(mid.map((s) => [s.label, s.from, s.to]), [["Mar", 0, 17], ["Apr", 17, 30]]);
  assert.deepStrictEqual(flow.monthSegments("nope", 30, presets.formatMonth), []);
});

test("upperBound counts the values at or below t", () => {
  const arr = Float64Array.from([1, 2, 2, 3]);
  assert.deepStrictEqual([0, 1, 2, 2.5, 3, 9].map((t) => flow.upperBound(arr, t)), [0, 1, 3, 3, 4, 4]);
});

// ---- renderer ---------------------------------------------------------------

test("render: heading, one label per group, counters that follow the scene time", () => {
  const { tl, container, result } = render();
  assert.strictEqual(result, tl);
  assert.strictEqual(find(container, "tw-cap-heading")[0].textContent, "Every commit, one block");
  const names = find(container, "tw-cap-name").map((e) => e.textContent);
  assert.deepStrictEqual(names, ["Core Alpha", "beta", "eta"]);
  const counts = () => find(container, "tw-cap-count").map((e) => e.textContent);
  assert.deepStrictEqual(counts(), ["0", "0", "0"]);
  const call = seek(tl, 30);
  assert.strictEqual(call.vars.duration, 30);
  assert.strictEqual(call.vars.ease, "none");
  assert.deepStrictEqual(counts(), ["5", "2", "0"]);
  seek(tl, 2.5 + (50 / 365) * 23.5);
  assert.deepStrictEqual(counts(), ["3", "1", "0"]);
  seek(tl, 0);
  assert.deepStrictEqual(counts(), ["0", "0", "0"]);
});

test("render: the legend lists only the categories present", () => {
  const { container } = render();
  assert.deepStrictEqual(find(container, "tw-cap-key-text").map((e) => e.textContent), ["Core", "Extension"]);
  const none = render(PARAMS, dataFor([group("x", undefined, [[1, 1]])])).container;
  assert.strictEqual(find(none, "tw-cap-legend").length, 0);
});

test("render: the month bar highlights the current month and fills with time", () => {
  const { tl, container } = render();
  const fill = find(container, "tw-cap-month-fill")[0];
  assert.strictEqual(find(container, "tw-cap-month").length, 12);
  seek(tl, 1);
  assert.strictEqual(find(container, "tw-cap-month tw-cap-month-on").length, 0);
  seek(tl, 2.5 + (40 / 365) * 23.5);
  assert.deepStrictEqual(find(container, "tw-cap-month tw-cap-month-on").map((e) => e.textContent), ["Feb"]);
  assert.strictEqual(fill.style.width, ((40 / 365) * 100).toFixed(2) + "%");
  seek(tl, 30);
  assert.deepStrictEqual(find(container, "tw-cap-month tw-cap-month-on").map((e) => e.textContent), ["Dec"]);
  assert.strictEqual(fill.style.width, "100.00%");
});

test("render: partial data shows a note; complete data does not", () => {
  assert.strictEqual(find(render().container, "tw-cap-partial").length, 0);
  const partial = render(PARAMS, dataFor(GROUPS), ["commit_flow.groups"]).container;
  assert.strictEqual(find(partial, "tw-cap-partial")[0].textContent, "partial data");
});

test("render: no groups, a missing window or a bad layout param do not crash", () => {
  const empty = render(PARAMS, { "commit_flow.groups": [], "commit_flow.window": {} });
  seek(empty.tl, 15);
  assert.strictEqual(find(empty.container, "tw-cap-label").length, 0);
  const odd = render(Object.assign({}, PARAMS, { layout: [{ group: "alpha" }, "x"] }), dataFor(GROUPS));
  seek(odd.tl, 20);
  assert.strictEqual(find(odd.container, "tw-cap-count")[0].textContent, "4");
});

test("render: labels are placed over the hexagons with a font that scales", () => {
  const { container } = render();
  const label = find(container, "tw-cap-label tw-cap-label-core")[0];
  assert.match(label.style.left, /px$/);
  assert.match(label.style.top, /px$/);
  assert.match(label.style.maxWidth, /px$/);
  const font = parseFloat(find(container, "tw-cap-name")[0].style.fontSize);
  assert.ok(font >= 9 && font <= 18);
});
