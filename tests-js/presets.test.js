const test = require("node:test");
const assert = require("node:assert");
const presets = require("../web/presets/presets.js");

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
