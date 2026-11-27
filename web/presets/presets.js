(function (root) {
  "use strict";

  const formatter = new Intl.NumberFormat("en-US");

  function format(n) {
    return formatter.format(n);
  }

  // Resolve "summary.totals.commits" against {dataset name: dataset}.
  // Dataset names are tried as the first two segments, then the first one.
  function lookup(data, ref) {
    const parts = ref.split(".");
    for (const take of [2, 1]) {
      const name = parts.slice(0, take).join(".");
      if (parts.length >= take && Object.prototype.hasOwnProperty.call(data, name)) {
        let node = data[name];
        for (const key of parts.slice(take)) {
          if (node === null || typeof node !== "object" || !(key in node)) return undefined;
          node = node[key];
        }
        return node;
      }
    }
    return undefined;
  }

  function isPartial(partial, ref) {
    return partial.some((name) => ref === name || ref.startsWith(name + "."));
  }

  function fadeIn(tl, targets, at = 0, duration = 0.6) {
    return tl.from(targets, { opacity: 0, y: 20, duration, ease: "power2.out" }, at);
  }

  function stagger(tl, targets, at = 0, each = 0.15, duration = 0.5) {
    return tl.from(targets, { opacity: 0, y: 24, duration, stagger: each, ease: "power2.out" }, at);
  }

  function popIn(tl, targets, at = 0, each = 0.05, duration = 0.35) {
    return tl.from(targets, { opacity: 0, scale: 0, duration, stagger: each, ease: "back.out(1.7)" }, at);
  }

  // Bubbles rise from below and from varied sides, then settle in place with a small bounce.
  // Offsets depend only on the target index, so scrubbing and replaying look identical.
  function bubbleIn(tl, targets, at = 0, each = 0.08, duration = 1.1) {
    return tl.from(targets, {
      opacity: 0,
      scale: 0.2,
      y: (i) => 160 + ((i * 53) % 90),
      x: (i) => ((i * 37) % 120) - 60,
      duration,
      stagger: each,
      ease: "elastic.out(1, 0.6)",
    }, at);
  }

  function countUp(tl, el, to, at = 0, duration = 1.2) {
    const state = { v: 0 };
    el.textContent = format(0);
    return tl.to(state, {
      v: to,
      duration,
      ease: "power1.out",
      onUpdate: () => { el.textContent = format(Math.round(state.v)); },
    }, at);
  }

  const api = { format, lookup, isPartial, fadeIn, stagger, popIn, bubbleIn, countUp };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.TeamWrapped = root.TeamWrapped || {};
    root.TeamWrapped.presets = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
