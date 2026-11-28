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

  // The element appears, swells past its final size, then settles back ("expand a bit, then contract a bit").
  function swellIn(tl, target, at = 0, peak = 1.25, duration = 0.55) {
    tl.fromTo(target, { opacity: 0, scale: 0 }, { opacity: 1, scale: peak, duration: duration * 0.55, ease: "power2.out" }, at);
    return tl.to(target, { scale: 1, duration: duration * 0.45, ease: "power2.inOut" }, at + duration * 0.55);
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

  // Drops targets in from above, bounces them on landing and squashes each one as it hits the ground.
  // `rise(i)` is how far above its final spot target i starts; depends only on the index, so replays look identical.
  function dropIn(tl, targets, at = 0, each = 0.08, rise = () => 400, duration = 0.9) {
    tl.fromTo(targets, { opacity: 0, y: (i) => -rise(i) },
      { opacity: 1, y: 0, duration, stagger: each, ease: "bounce.out" }, at);
    // bounce.out first touches the ground at 1/2.75 of its duration; squash then spring back
    const land = at + duration * 0.36;
    tl.to(targets, { scaleX: 1.15, scaleY: 0.8, duration: 0.08, stagger: each, ease: "power2.out" }, land);
    return tl.to(targets, { scaleX: 1, scaleY: 1, duration: 0.4, stagger: each, ease: "elastic.out(1, 0.5)" }, land + 0.08);
  }

  // Name label metrics for an avatar of `size`: one line, font scaling with the avatar (never under 9px),
  // 1.6 avatars wide, starting `offset` below the avatar centre.
  function nameLabel(size) {
    const font = Math.max(9, Math.round(size * 0.16 * 10) / 10);
    const gap = Math.max(2, size * 0.05);
    return { font, width: size * 1.6, height: font * 1.3, offset: size / 2 + gap };
  }

  // Scatters `count` avatars loosely over width x height without overlap: a grid of roomy cells, each avatar
  // jittered inside its cell, cells visited in a fixed scrambled order. Returns {size, points: [{x, y}]} (centres).
  // Deterministic, and the avatar size shrinks as the count grows so large teams fit.
  // With `{labels: true}` each cell also holds a name label under its avatar (see nameLabel): cells grow to fit
  // avatar plus label, so no avatar or label overlaps another, and the result carries `label` metrics.
  function scatterLayout(count, width, height, maxSize = 120, minSize = 20, options = {}) {
    if (!(count > 0)) return { size: 0, points: [] };
    const labels = Boolean(options && options.labels);
    // The box one item needs (avatar, plus its label when labelled) and the cell it is jittered in.
    const box = (s) => {
      if (!labels) return { w: s, h: s, cellW: s * 1.25, cellH: s * 1.25 };
      const label = nameLabel(s);
      const w = label.width;
      const h = label.offset + label.height + s / 2;
      return { w, h, cellW: w + s * 0.2, cellH: h + s * 0.2 };
    };
    let size = minSize;
    let cols = 1;
    let rows = count;
    for (let s = maxSize; s >= minSize; s -= 2) {
      const b = box(s);
      const c = Math.max(1, Math.floor(width / b.cellW));
      const r = Math.ceil(count / c);
      if (r * b.cellH <= height) { size = s; cols = c; rows = r; break; }
      if (s - 2 < minSize) { size = minSize; cols = c; rows = r; }
    }
    const { w, h, cellW, cellH } = box(size);
    const total = cols * rows;
    const gcd = (a, b) => (b === 0 ? a : gcd(b, a % b));
    let step = Math.max(1, Math.round(total * 0.618));
    while (gcd(step, total) !== 1) step++;
    const left = (width - cols * cellW) / 2;
    const top = Math.max(0, (height - rows * cellH) / 2);
    const jitter = (i, k, slack) => (((Math.imul(i + 1, k) >>> 0) % 1000) / 1000 - 0.5) * slack;
    const points = [];
    for (let i = 0; i < count; i++) {
      const at = (i * step) % total;
      points.push({
        x: left + (at % cols + 0.5) * cellW + jitter(i, 2654435761, cellW - w),
        // the avatar sits at the top of its box, the label (if any) under it
        y: top + (Math.floor(at / cols) + 0.5) * cellH + jitter(i, 40503, cellH - h) - (h - size) / 2,
      });
    }
    return labels ? { size, points, label: nameLabel(size) } : { size, points };
  }

  // Schedules the main count and the tail beats on `tl`, calling show(v) whenever the value changes.
  // `beat` is {duration, ease} for the single-increment tail beats.
  function scheduleCount(tl, to, at, duration, ease, tail, show, beat) {
    const state = { v: 0 };
    const update = () => show(state.v);
    // Tail beats: the last few increments land one at a time, each after its own pause.
    const pauses = (Array.isArray(tail) ? tail : [])
      .filter((p) => typeof p === "number" && Number.isFinite(p) && p > 0)
      .slice(0, Math.max(0, Math.round(to)));
    const main = to - pauses.length;
    tl.to(state, { v: main, duration, ease, onUpdate: update }, at);
    let when = at + duration;
    pauses.forEach((pause, i) => {
      when += pause;
      tl.to(state, { v: main + i + 1, duration: Math.min(beat.duration, pause), ease: beat.ease, onUpdate: update }, when);
    });
    return tl;
  }

  function countUp(tl, el, to, at = 0, duration = 1.2, ease = "power1.out", tail = []) {
    el.textContent = format(0);
    return scheduleCount(tl, to, at, duration, ease, tail,
      (v) => { el.textContent = format(Math.round(v)); }, { duration: 0.05, ease: "none" });
  }

  // Where each wheel of a mechanical counter sits for the value v, in digits (0 to 10; index 0 = units).
  // The units wheel turns continuously; every other wheel only turns while the wheel below it passes 9 to 0.
  function wheelPositions(v, wheels) {
    const out = [];
    for (let k = 0; k < wheels; k++) {
      if (k === 0) {
        out.push(((v % 10) + 10) % 10);
      } else {
        const base = Math.floor(v / Math.pow(10, k)) % 10;
        out.push(base + Math.max(0, out[k - 1] - 9));
      }
    }
    return out;
  }

  // An odometer: a row of digit wheels that roll upward as the value counts up.
  function odometer(tl, el, to, at = 0, duration = 1.2, ease = "power1.out", tail = [],
    doc = typeof document !== "undefined" ? document : null) {
    const total = Number.isFinite(to) && to > 0 ? Math.round(to) : 0;
    const count = String(total).length;
    const root = doc.createElement("span");
    root.className = "tw-odo";
    const wheels = [];                                   // index = wheel number, 0 = units
    for (let k = count - 1; k >= 0; k--) {
      const wheel = doc.createElement("span");
      wheel.className = "tw-odo-wheel";
      const strip = doc.createElement("span");
      strip.className = "tw-odo-strip";
      for (let d = 0; d <= 10; d++) {                    // 0 to 9, then 0 again so 9 can roll into 0
        const cell = doc.createElement("span");
        cell.className = "tw-odo-digit";
        cell.textContent = String(d % 10);
        strip.append(cell);
      }
      wheel.append(strip);
      root.append(wheel);
      wheels[k] = { wheel, strip };
      if (k > 0 && k % 3 === 0) {
        const sep = doc.createElement("span");
        sep.className = "tw-odo-sep";
        sep.textContent = ",";
        root.append(sep);
      }
    }
    el.textContent = "";
    el.append(root);
    if (typeof el.setAttribute === "function") {
      el.setAttribute("role", "img");
      el.setAttribute("aria-label", format(total));
      root.setAttribute("aria-hidden", "true");
    }
    const show = (v) => {
      const value = Math.min(Math.max(v, 0), total);
      const positions = wheelPositions(value, count);
      positions.forEach((pos, k) => {
        wheels[k].strip.style.transform = "translateY(" + (-pos * 100 / 11) + "%)";
        // leading zero wheels (not the units wheel) are dimmed, like unused digits on a pump counter
        wheels[k].wheel.style.opacity = k > 0 && Math.floor(value / Math.pow(10, k)) === 0 && pos === 0 ? "0.3" : "1";
      });
    };
    show(0);
    return scheduleCount(tl, total, at, duration, ease, tail, show, { duration: 0.3, ease: "power2.inOut" });
  }

  // Largest folder size (px) whose grid of `count` folders fits in width x height.
  function fitFolderSize(count, width, height) {
    for (let size = 128; size >= 36; size -= 2) {
      const gapX = size * 0.14;
      const gapY = size * 0.2;
      const cols = Math.max(1, Math.floor((width + gapX) / (size + gapX)));
      const rows = Math.ceil(count / cols);
      const needed = rows * (size * 0.75) + (rows - 1) * gapY;
      if (needed <= height) return { size, font: Math.max(5, Math.round(size * 0.1 * 10) / 10) };
    }
    return { size: 36, font: 5 };
  }

  // Separate parts joined by hand, so older ICU/CLDR versions cannot add a comma after the weekday.
  const WEEKDAY = new Intl.DateTimeFormat("en-GB", { weekday: "long", timeZone: "UTC" });
  const DAY_NUM = new Intl.DateTimeFormat("en-GB", { day: "numeric", timeZone: "UTC" });
  const MONTH = new Intl.DateTimeFormat("en-GB", { month: "long", timeZone: "UTC" });

  // "2026-03-14" -> "Saturday 14 March" (or "14 March" without the weekday); other values are returned unchanged.
  function formatDate(iso, withWeekday = true) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso));
    if (!m) return iso;
    const date = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    if (date.getUTCMonth() !== +m[2] - 1 || date.getUTCDate() !== +m[3]) return iso;     // impossible date
    const dayMonth = `${DAY_NUM.format(date)} ${MONTH.format(date)}`;
    return withWeekday ? `${WEEKDAY.format(date)} ${dayMonth}` : dayMonth;
  }

  // "2026-03" -> "March"; other values are returned unchanged.
  function formatMonth(iso) {
    const m = /^(\d{4})-(\d{2})$/.exec(String(iso));
    if (!m || +m[2] < 1 || +m[2] > 12) return iso;
    return MONTH.format(new Date(Date.UTC(+m[1], +m[2] - 1, 1)));
  }

  // Replaces {key} in a template with the record's value, formatted by key; {key:one|many} adds the number and picks the form.
  // Dates carry no year because the wrap covers one calendar year.
  const FIELD_FORMATS = {
    date: (v) => formatDate(v, true),
    from: (v) => formatDate(v, false),
    to: (v) => formatDate(v, false),
    month: (v) => formatMonth(v),
  };
  function fillTemplate(template, record) {
    const has = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);
    const rec = record !== null && typeof record === "object" ? record : {};
    return String(template).replace(/\{(\w+)(?::([^|}]*)\|([^}]*))?\}/g, (_, key, singular, plural) => {
      const value = has(rec, key) ? rec[key] : undefined;
      if (value === undefined || value === null) return "";
      if (singular !== undefined) {                                      // {key:singular|plural}
        if (typeof value !== "number") return "";
        return format(value) + " " + (value === 1 ? singular : plural);
      }
      if (has(FIELD_FORMATS, key)) return FIELD_FORMATS[key](String(value));
      if (/_number$/.test(key)) return String(value);                    // ids are never given thousands separators
      return typeof value === "number" ? format(value) : String(value);
    });
  }

  const api = { format, lookup, isPartial, fadeIn, stagger, popIn, swellIn, bubbleIn, dropIn, scatterLayout, nameLabel, countUp, wheelPositions, odometer, fitFolderSize, formatDate, formatMonth, fillTemplate };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.TeamWrapped = root.TeamWrapped || {};
    root.TeamWrapped.presets = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
