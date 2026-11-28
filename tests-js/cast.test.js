const test = require("node:test");
const assert = require("node:assert");
const presets = require("../web/presets/presets.js");
const { makeEl, loadRenderer, fakeTimeline, find } = require("./helpers.js");

const person = (login, kind) => ({ login, kind, avatar_file: `avatars/${login || "x"}.png` });
const PEOPLE = [
  person("ada", "human"), person("alan", "human"), person(null, "unlinked"),
  person("build-bot", "bot"), person("lint-bot", "bot"),
];
const dataFor = (list) => ({ contributors: { total: list.length, list } });
const PARAMS = {
  stages: [
    { heading: "All done by {count:contributor|contributors}", kinds: ["human", "unlinked"] },
    { heading: "… and {count:robot|robots}", kinds: ["bot"] },
  ],
};
const round2 = (n) => Math.round(n * 100) / 100;

function render(params = PARAMS, data = dataFor(PEOPLE), elDefaults = {}) {
  const tl = fakeTimeline();
  const container = makeEl("section");
  const result = loadRenderer("cast", elDefaults).render({
    container, data, params, partial: [], duration: 14, gsap: { timeline: () => tl }, presets,
  });
  return { tl, container, result };
}

// Run the count-ups only; the other `to` tweens carry no onUpdate.
const finishCounts = (tl) => tl.calls.filter((c) => c.kind === "to" && c.vars.onUpdate)
  .forEach((c) => { c.target.v = c.vars.v; c.vars.onUpdate(); });
const headingText = (el) => el.children.map((c) => c.textContent).join("");

test("the headings wrap the highlighted count and pick the singular or plural word", () => {
  const { tl, container, result } = render();
  assert.strictEqual(result, tl);
  finishCounts(tl);
  const [h1, h2] = find(container, "tw-cast-heading").concat(find(container, "tw-cast-heading tw-cast-heading-late"));
  assert.strictEqual(headingText(h1), "All done by 3 contributors");
  assert.strictEqual(headingText(h2), "… and 2 robots");
  assert.deepStrictEqual(find(container, "tw-cast-count").map((e) => e.textContent), ["3", "2"]);
  const one = render(PARAMS, dataFor([person("solo", "human"), person("b", "bot")]));
  finishCounts(one.tl);
  assert.strictEqual(headingText(find(one.container, "tw-cast-heading")[0]), "All done by 1 contributor");
  assert.strictEqual(headingText(find(one.container, "tw-cast-heading tw-cast-heading-late")[0]), "… and 1 robot");
});

test("there is one image per person, humans first, with the login or a fallback as alt text", () => {
  const { container } = render();
  const faces = find(container, "tw-cast-face");
  assert.deepStrictEqual(faces.map((f) => f.src), PEOPLE.map((p) => p.avatar_file));
  assert.deepStrictEqual(faces.map((f) => f.alt),
    ["ada", "alan", "contributor without a GitHub account", "build-bot", "lint-bot"]);
});

test("the avatars are placed at distinct spots", () => {
  const { container } = render();
  const spots = find(container, "tw-cast-face").map((f) => f.style.left + "," + f.style.top);
  assert.strictEqual(new Set(spots).size, 5);
});

test("the humans drop in first, the robots only after a hold, and the robot heading rises from below", () => {
  const { tl, container } = render();
  const [humans, bots] = tl.calls.filter((c) => c.kind === "fromTo" && Array.isArray(c.targets));
  assert.strictEqual(humans.targets.length, 3);
  assert.strictEqual(bots.targets.length, 2);
  assert.ok(bots.at - humans.at >= 0.9 + 3, "a few seconds to find yourself after the last drop lands");
  const rise = tl.calls.find((c) => c.kind === "fromTo" && c.targets === find(container, "tw-cast-heading tw-cast-heading-late")[0]);
  assert.ok(rise.from.y > 0 && rise.vars.y === 0);
  assert.ok(rise.at < bots.at && rise.at > humans.at + 3);
});

test("the humans stay visible: they shrink and shift up when the robot stage starts", () => {
  const crowd = Array.from({ length: 60 }, (_, i) => person(`p${i}`, "human")).concat(PEOPLE.slice(3));
  const { tl } = render(PARAMS, dataFor(crowd));
  const [humans] = tl.calls.filter((c) => c.kind === "fromTo" && Array.isArray(c.targets));
  const rise = tl.calls.find((c) => c.kind === "fromTo" && !Array.isArray(c.targets) && c.from.y > 0);
  const move = tl.calls.find((c) => c.kind === "to" && c.target === humans.targets && c.vars.x);
  assert.ok(move);
  assert.strictEqual(round2(move.at), round2(rise.at));
  assert.ok(move.vars.scale < 1);
  const shifts = humans.targets.map((_, i) => move.vars.y(i));
  assert.ok(shifts.reduce((a, b) => a + b, 0) / shifts.length < 0, "the group moves up on average");
});

test("the moved humans end up clear of the robots, and nobody leaves the arena", () => {
  const defaults = { clientWidth: 800, clientHeight: 500 };
  const { tl, container } = render(PARAMS, dataFor(PEOPLE), defaults);
  const [humans] = tl.calls.filter((c) => c.kind === "fromTo" && Array.isArray(c.targets));
  const move = tl.calls.find((c) => c.kind === "to" && c.target === humans.targets && c.vars.x);
  const faces = find(container, "tw-cast-face");
  const box = (img, i, moved) => {
    const size = parseFloat(img.style.width) * (moved ? move.vars.scale : 1);
    const cx = parseFloat(img.style.left) + parseFloat(img.style.width) / 2 + (moved ? move.vars.x(i) : 0);
    const cy = parseFloat(img.style.top) + parseFloat(img.style.height) / 2 + (moved ? move.vars.y(i) : 0);
    return { cx, cy, size };
  };
  const humanBoxes = faces.slice(0, 3).map((f, i) => box(f, i, true));
  const botBoxes = faces.slice(3).map((f, i) => box(f, i, false));
  const lowestHuman = Math.max(...humanBoxes.map((b) => b.cy + b.size / 2));
  const highestBot = Math.min(...botBoxes.map((b) => b.cy - b.size / 2));
  assert.ok(lowestHuman <= highestBot - 48 + 1e-9, "the robot heading band fits between them");
  [...humanBoxes, ...botBoxes].forEach((b) => assert.ok(b.cy - b.size / 2 >= -1e-9 && b.cy + b.size / 2 <= 500 + 1e-9));
});

test("with no robots the second stage and its heading are skipped", () => {
  const { tl, container } = render(PARAMS, dataFor(PEOPLE.slice(0, 3)));
  assert.strictEqual(find(container, "tw-cast-heading tw-cast-heading-late").length, 0);
  assert.strictEqual(find(container, "tw-cast-face").length, 3);
  assert.strictEqual(tl.calls.filter((c) => c.kind === "fromTo" && Array.isArray(c.targets)).length, 1);
  assert.strictEqual(tl.calls.filter((c) => c.kind === "to" && c.vars.scale !== undefined).length, 0);
});

test("a team of nobody still shows the first heading with 0", () => {
  const { tl, container } = render(PARAMS, dataFor([]));
  finishCounts(tl);
  assert.strictEqual(headingText(find(container, "tw-cast-heading")[0]), "All done by 0 contributors");
  assert.strictEqual(find(container, "tw-cast-face").length, 0);
});

test("the drop stagger is capped so a big team does not overrun the scene", () => {
  const crowd = Array.from({ length: 400 }, (_, i) => person(`p${i}`, "human"));
  const { tl } = render(PARAMS, dataFor(crowd));
  const drop = tl.calls.find((c) => c.kind === "fromTo" && Array.isArray(c.targets));
  assert.ok(drop.vars.stagger * 400 <= 2.5 + 1e-9);
});

test("everything is on one timeline that is built from the data alone, so replays are identical", () => {
  const a = render().tl.calls.map((c) => [c.kind, round2(c.at)]);
  const b = render().tl.calls.map((c) => [c.kind, round2(c.at)]);
  assert.deepStrictEqual(a, b);
});

test("the heading carries a plain-text label for screen readers", () => {
  const { container } = render();
  assert.strictEqual(find(container, "tw-cast-heading")[0].getAttribute("aria-label"), "All done by 3 contributors");
});

const bot = (login, name) => ({ ...person(login, "bot"), ...(name === undefined ? {} : { name }) });
const NAMED = {
  stages: [PARAMS.stages[0], { ...PARAMS.stages[1], names: true }],
};
const px = (v) => parseFloat(v);
const centre = (img) => ({ x: px(img.style.left) + px(img.style.width) / 2, y: px(img.style.top) + px(img.style.height) / 2 });

test("a stage with names: true shows each bot's name under its avatar; the humans stage has no labels", () => {
  const people = PEOPLE.slice(0, 3).concat([bot("sample-bot[bot]", "sample-bot"), bot("helper-bot[bot]", "helper-bot")]);
  const { container } = render(NAMED, dataFor(people), { clientWidth: 1000, clientHeight: 520 });
  const labels = find(container, "tw-cast-name");
  assert.deepStrictEqual(labels.map((l) => l.textContent), ["sample-bot", "helper-bot"]);
  const faces = find(container, "tw-cast-face").slice(3);
  labels.forEach((label, i) => {
    const c = centre(faces[i]);
    const size = px(faces[i].style.width);
    assert.ok(Math.abs(px(label.style.left) + px(label.style.width) / 2 - c.x) < 1e-6, "centred under the avatar");
    assert.ok(px(label.style.top) >= c.y + size / 2, "below the avatar");
    assert.ok(Math.abs(px(label.style.width) - 1.6 * size) < 1e-6);
    assert.ok(px(label.style.fontSize) >= 9);
    assert.strictEqual(label.getAttribute("aria-hidden"), "true");
  });
});

test("without names: true there are no labels, and the scene data does not need names", () => {
  const people = PEOPLE.slice(0, 3).concat([bot("sample-bot[bot]", "sample-bot")]);
  assert.strictEqual(find(render(PARAMS, dataFor(people)).container, "tw-cast-name").length, 0);
  assert.strictEqual(find(render(NAMED, dataFor(PEOPLE)).container, "tw-cast-name").length, 0);   // nobody has a name
});

test("a contributor without a name gets no label, the others still do", () => {
  const people = [person("ada", "human"), bot("sample-bot[bot]", "sample-bot"), bot("odd-bot[bot]"), bot("blank[bot]", "")];
  const { container } = render(NAMED, dataFor(people));
  assert.deepStrictEqual(find(container, "tw-cast-name").map((l) => l.textContent), ["sample-bot"]);
  assert.strictEqual(find(container, "tw-cast-face").length, 4);
});

test("a single robot gets its label, and labels drop in with their avatars just after them", () => {
  const { tl, container } = render(NAMED, dataFor([person("ada", "human"), bot("sample-bot[bot]", "sample-bot")]));
  const labels = find(container, "tw-cast-name");
  assert.strictEqual(labels.length, 1);
  const drops = tl.calls.filter((c) => c.kind === "fromTo" && Array.isArray(c.targets));
  const robots = drops.find((c) => c.targets.length === 1 && c.targets[0].className === "tw-cast-face" && c.targets[0].src.includes("sample-bot"));
  const names = drops.find((c) => c.targets[0] === labels[0]);
  assert.ok(names.at > robots.at && names.at - robots.at <= 0.3, "a slight delay after the avatar");
  assert.strictEqual(names.vars.opacity, 0.8);
  assert.ok(names.from.y(0) < 0 && names.vars.y === 0);
  assert.strictEqual(names.vars.stagger(0), 0);
});

test("labels of an earlier stage move with their avatars when a later stage arrives", () => {
  const params = { stages: [{ ...PARAMS.stages[1], names: true }, PARAMS.stages[0]] };
  const people = Array.from({ length: 12 }, (_, i) => bot(`bot-${i}[bot]`, `bot-${i}`))
    .concat(Array.from({ length: 30 }, (_, i) => person(`p${i}`, "human")));
  const { tl, container } = render(params, dataFor(people), { clientWidth: 800, clientHeight: 500 });
  const labels = find(container, "tw-cast-name");
  const [bots] = tl.calls.filter((c) => c.kind === "fromTo" && Array.isArray(c.targets));
  const faceMove = tl.calls.find((c) => c.kind === "to" && c.target === bots.targets && c.vars.x);
  const labelMove = tl.calls.find((c) => c.kind === "to" && Array.isArray(c.target) && c.target[0] === labels[0] && c.vars.x);
  assert.ok(labelMove);
  assert.strictEqual(round2(labelMove.at), round2(faceMove.at));
  labels.forEach((label, i) => {
    assert.ok(Math.abs(labelMove.vars.x(i) - faceMove.vars.x(i)) < 1e-6, "same sideways shift as the avatar");
    const face = bots.targets[i];
    const movedFaceBottom = centre(face).y + faceMove.vars.y(i) + (px(face.style.width) * faceMove.vars.scale) / 2;
    assert.ok(px(label.style.top) + labelMove.vars.y(i) >= movedFaceBottom - 1e-6, "still under the moved avatar");
  });
  assert.ok(labelMove.vars.scale < 1 && labelMove.vars.scale === faceMove.vars.scale);
});
