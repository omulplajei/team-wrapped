const test = require("node:test");
const assert = require("node:assert");
const { makeCtx, fakeTimeline, loadRenderer, find } = require("./helpers.js");

function render(params, theme = null) {
  const tl = fakeTimeline();
  const ctx = makeCtx({ tl, params, theme });
  const result = loadRenderer("message").render(ctx);
  return { tl, container: ctx.container, result };
}

const FULL = { text: "Thank you", subtext: "To everyone", logo: "color" };
const THEME = { logos: { color: "assets/theme/logo.png" } };

test("a plain message is one heading, as before", () => {
  const { tl, container, result } = render({ text: "Hello" });
  assert.strictEqual(result, tl);
  assert.strictEqual(container.children.length, 1);
  assert.strictEqual(container.children[0].className, "tw-message");
  assert.strictEqual(container.children[0].textContent, "Hello");
  assert.strictEqual(tl.calls.length, 1);
  assert.strictEqual(tl.calls[0].targets, container.children[0]);
});

test("heading, subtext and logo are stacked in a wrapper, the logo first", () => {
  const { container } = render(FULL, THEME);
  const [wrap] = container.children;
  assert.strictEqual(wrap.className, "tw-message-scene");
  assert.deepStrictEqual(wrap.children.map((e) => e.className), ["tw-message-logo", "tw-message", "tw-message-sub"]);
  assert.strictEqual(wrap.children[0].attributes.src, "assets/theme/logo.png");
  assert.strictEqual(wrap.children[0].attributes.alt, "");
  assert.strictEqual(wrap.children[1].textContent, "Thank you");
  assert.strictEqual(wrap.children[2].textContent, "To everyone");
});

test("the logo pops in first, then the heading fades up, then the subtext", () => {
  const { tl, container } = render(FULL, THEME);
  const [logo, heading, sub] = container.children[0].children;
  const at = (target) => Math.min(...tl.calls.filter((c) => c.targets === target || c.target === target).map((c) => c.at));
  assert.ok(at(logo) < at(heading) && at(heading) < at(sub));
  assert.ok(tl.calls.some((c) => c.kind === "fromTo" && c.targets === logo && c.from.scale === 0));
});

test("without a theme, or with a theme lacking that logo, only the text shows", () => {
  for (const theme of [null, undefined, {}, { logos: {} }, { logos: { mono: "assets/theme/m.png" } }]) {
    const { container } = render(FULL, theme);
    assert.strictEqual(find(container, "tw-message-logo").length, 0);
    assert.strictEqual(find(container, "tw-message")[0].textContent, "Thank you");
    assert.strictEqual(find(container, "tw-message-sub")[0].textContent, "To everyone");
  }
});

test("a subtext alone, or a logo name that is not a string, never errors", () => {
  assert.strictEqual(find(render({ text: "Hi", subtext: "there" }).container, "tw-message-sub").length, 1);
  assert.strictEqual(find(render({ text: "Hi", logo: 5 }, THEME).container, "tw-message-logo").length, 0);
  assert.strictEqual(find(render({ text: "Hi", subtext: "" }).container, "tw-message-sub").length, 0);
  assert.strictEqual(find(render({ text: "Hi", logo: "constructor" }, THEME).container, "tw-message-logo").length, 0);
});
