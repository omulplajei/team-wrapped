const test = require("node:test");
const assert = require("node:assert");
const timing = require("../web/player/timing.js");

test("offsets gives start and end of every scene", () => {
  assert.deepStrictEqual(timing.offsets([4, 6, 10]), [
    { start: 0, end: 4 },
    { start: 4, end: 10 },
    { start: 10, end: 20 },
  ]);
});

test("total adds durations", () => {
  assert.strictEqual(timing.total([4, 6, 10]), 20);
});

test("sceneAt finds the scene and the progress inside it", () => {
  const d = [4, 6, 10];
  assert.deepStrictEqual(timing.sceneAt(d, 0), { index: 0, progress: 0 });
  assert.deepStrictEqual(timing.sceneAt(d, 4), { index: 1, progress: 0 });
  assert.deepStrictEqual(timing.sceneAt(d, 7), { index: 1, progress: 0.5 });
});

test("sceneAt clamps before the start and after the end", () => {
  const d = [4, 6, 10];
  assert.deepStrictEqual(timing.sceneAt(d, -3), { index: 0, progress: 0 });
  assert.deepStrictEqual(timing.sceneAt(d, 99), { index: 2, progress: 1 });
  assert.deepStrictEqual(timing.sceneAt(d, 20), { index: 2, progress: 1 });
});

test("elapsed is the inverse of sceneAt", () => {
  const d = [4, 6, 10];
  assert.strictEqual(timing.elapsed(d, 1, 0.5), 7);
  assert.strictEqual(timing.elapsed(d, 0, 0), 0);
  assert.strictEqual(timing.elapsed(d, 2, 1), 20);
});
