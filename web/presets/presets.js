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

  // Replaces {key} in a template with the record's value, formatted by key.
  const FIELD_FORMATS = {
    date: (v) => formatDate(v, true),
    from: (v) => formatDate(v, false),
    to: (v) => formatDate(v, false),
    month: (v) => formatMonth(v),
  };
  function fillTemplate(template, record) {
    const has = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);
    const rec = record !== null && typeof record === "object" ? record : {};
    return String(template).replace(/\{(\w+)\}/g, (_, key) => {
      const value = has(rec, key) ? rec[key] : undefined;
      if (value === undefined || value === null) return "";
      if (has(FIELD_FORMATS, key)) return FIELD_FORMATS[key](String(value));
      if (/_number$/.test(key)) return String(value);                    // ids are never given thousands separators
      return typeof value === "number" ? format(value) : String(value);
    });
  }

  const api = { format, lookup, isPartial, fadeIn, stagger, popIn, swellIn, bubbleIn, countUp, wheelPositions, odometer, fitFolderSize, formatDate, formatMonth, fillTemplate };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.TeamWrapped = root.TeamWrapped || {};
    root.TeamWrapped.presets = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
