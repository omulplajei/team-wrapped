const fs = require("node:fs");
const path = require("node:path");

// A minimal DOM: just enough for the renderers, which only build elements.
function makeEl(tag) {
  const el = { tag, className: "", textContent: "", children: [], style: { setProperty(k, v) { this[k] = v; } } };
  el.append = (...kids) => { el.children.push(...kids); };
  el.appendChild = (kid) => { el.children.push(kid); return kid; };
  return el;
}

// Load render.js the way the build does: `export default` becomes an assignment.
function loadRenderer(type, elDefaults = {}) {
  const file = path.join(__dirname, "..", "web", "scene-types", type, "render.js");
  const source = fs.readFileSync(file, "utf8").replace("export default", "module.exports =");
  const module = { exports: {} };
  new Function("module", "document", source)(module, { createElement: (tag) => Object.assign(makeEl(tag), elDefaults) });
  return module.exports;
}

function fakeTimeline() {
  const calls = [];
  const tl = {
    calls,
    from: (targets, vars, at) => { calls.push({ kind: "from", targets, vars, at }); return tl; },
    fromTo: (targets, from, vars, at) => { calls.push({ kind: "fromTo", targets, from, vars, at }); return tl; },
    to: (target, vars, at) => { calls.push({ kind: "to", target, vars, at }); return tl; },
  };
  return tl;
}

function find(el, className, found = []) {
  if (el.className === className) found.push(el);
  (el.children || []).forEach((kid) => find(kid, className, found));
  return found;
}

// Run every count-up to its end so the elements show their final text.
function finishCountUps(tl) {
  tl.calls.filter((c) => c.kind === "to").forEach((c) => { c.target.v = c.vars.v; c.vars.onUpdate(); });
}

module.exports = { makeEl, loadRenderer, fakeTimeline, find, finishCountUps };
