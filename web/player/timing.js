(function (root) {
  "use strict";

  function offsets(durations) {
    let t = 0;
    return durations.map((d) => {
      const start = t;
      t += d;
      return { start, end: t };
    });
  }

  function total(durations) {
    return durations.reduce((a, b) => a + b, 0);
  }

  function sceneAt(durations, seconds) {
    const t = Math.min(Math.max(seconds, 0), total(durations));
    const o = offsets(durations);
    for (let i = 0; i < o.length; i++) {
      if (t < o[i].end || i === o.length - 1) {
        const progress = durations[i] === 0 ? 1 : Math.min((t - o[i].start) / durations[i], 1);
        return { index: i, progress };
      }
    }
  }

  function elapsed(durations, index, progress) {
    return offsets(durations)[index].start + durations[index] * progress;
  }

  const api = { offsets, total, sceneAt, elapsed };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.TeamWrapped = root.TeamWrapped || {};
    root.TeamWrapped.timing = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
