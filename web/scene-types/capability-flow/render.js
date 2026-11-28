// capability-flow: every commit of the year falls as a block into its capability's hexagon and stays there.
//
// Geometry is computed once, up front, in hexagon-local normalised units: a hexagon (flat top and bottom,
// pointed left and right) is 1 wide (circumradius 0.5) and HEX_H = sqrt(3)/2 tall; x runs from its left
// corner, y up from its bottom edge. Rendering only scales these numbers, so a resize never re-packs.
//
// Block size: side = clamp(k * sqrt(lines), MIN_SIDE, MAX_SIDE), so a block's area grows with its lines
// (0-line commits get MIN_SIDE; a huge commit is a slab, never wider than MAX_SIDE of the hexagon).
// One k is shared by every hexagon, chosen by bisection so that the busiest group's total block area,
// sum(side^2), is FILL (half) of the hexagon area 3*sqrt(3)/8: busy capabilities fill up, quiet ones stay low.
//
// Piles: deterministic skyline packing. Each block tries a few x positions picked by a hash of
// (group, commit), lands on the highest point of the height map under its width, takes the lowest of those
// landings and stays inside the hexagon at that height; a block that would poke out of the top is squeezed in.

const SQRT3 = Math.sqrt(3);
const HEX_H = SQRT3 / 2;
const HEX_AREA = (3 * SQRT3) / 8;
const FILL = 0.5;
const MIN_SIDE = 0.006;
const MAX_SIDE = 0.33;
const INSET = 0.012;          // keeps blocks clear of the outline
const CELLS = 240;            // height map resolution across the hexagon
const TRIES = 10;             // hashed x candidates per block
const GAP = 0.94;             // drawn hexagon radius / honeycomb cell radius
const FALL = 0.45;            // seconds a block takes to fall and settle
const FLASH = 0.7;            // seconds a big commit's ring lasts
const PULSE = 0.5;            // seconds a hexagon pulses after a big commit lands
const MIN_PX = 1.5;           // smallest block drawn, in CSS pixels
const CATEGORIES = ["core", "extension", "support"];
const CATEGORY_NAMES = { core: "Core", extension: "Extension", support: "Support" };

function hash01(a, b, salt) {
  let h = Math.imul(a + 1, 0x9e3779b1) ^ Math.imul(b + 1, 0x85ebca77) ^ Math.imul(salt + 1, 0xc2b2ae3d);
  h ^= h >>> 16; h = Math.imul(h, 0x7feb352d);
  h ^= h >>> 15; h = Math.imul(h, 0x846ca68b);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}

function categoryOf(group) {
  return group && CATEGORIES.includes(group.category) ? group.category : "none";
}

// Half the interior width of the hexagon at height y (0.25 at the flat top and bottom, 0.5 at the corners).
function hexHalfWidth(y) {
  const mid = HEX_H / 2;
  return 0.25 + 0.25 * Math.max(0, 1 - Math.abs(y - mid) / mid);
}

// Fits n hexagons in width x height as a honeycomb: columns 1.5 radii apart, every other one shifted down
// half a row. Picks the column count giving the largest hexagons; the most central cells go to order[0],
// order[1], ... Returns {radius (drawn), cell (honeycomb radius), centres: [{x, y}] indexed by item}.
function honeycombLayout(n, width, height, order, maxRadius = Infinity) {
  if (!(n > 0) || !(width > 0) || !(height > 0)) return { radius: 0, cell: 0, centres: [] };
  const sequence = Array.isArray(order) && order.length === n ? order : Array.from({ length: n }, (_, i) => i);
  let best = null;
  for (let cols = 1; cols <= n; cols++) {
    const rows = Math.ceil(n / cols);
    const r = Math.min(width / (1.5 * cols + 0.5), height / (SQRT3 * (rows + (cols > 1 ? 0.5 : 0))), maxRadius);
    if (!best || r > best.r * (1 + 1e-9)) best = { r, cols, rows };
  }
  const { r, cols, rows } = best;
  const slots = [];
  for (let c = 0; c < cols; c++) {
    for (let k = 0; k < rows; k++) {
      slots.push({ c, k, x: r + c * 1.5 * r, y: (SQRT3 / 2) * r + k * SQRT3 * r + (c % 2 ? (SQRT3 / 2) * r : 0) });
    }
  }
  const gx = (r * (1.5 * cols + 0.5)) / 2;
  const gy = (SQRT3 * r * (rows + (cols > 1 ? 0.5 : 0))) / 2;
  const dist = (s) => Math.hypot(s.x - gx, s.y - gy);
  slots.sort((a, b) => dist(a) - dist(b) || Math.abs(a.x - gx) - Math.abs(b.x - gx) || a.c - b.c || a.k - b.k);
  const chosen = slots.slice(0, n);
  return centred(chosen.map((s) => ({ x: s.x, y: s.y })), sequence, r, width, height);
}

// Shifts placed cells so their bounding box sits in the middle of width x height.
function centred(points, sequence, r, width, height) {
  const minX = Math.min(...points.map((p) => p.x)) - r;
  const maxX = Math.max(...points.map((p) => p.x)) + r;
  const minY = Math.min(...points.map((p) => p.y)) - (SQRT3 / 2) * r;
  const maxY = Math.max(...points.map((p) => p.y)) + (SQRT3 / 2) * r;
  const dx = (width - (maxX - minX)) / 2 - minX;
  const dy = (height - (maxY - minY)) / 2 - minY;
  const centres = new Array(points.length);
  points.forEach((p, k) => { centres[sequence[k]] = { x: p.x + dx, y: p.y + dy }; });
  return { radius: r * GAP, cell: r, centres };
}

// A hand-made layout from the `layout` param: [{group, col, row}], row in half steps. Bad entries are
// ignored; the layout is used only when every group has a good entry and no two cells overlap (else null).
function overrideLayout(names, entries, width, height, maxRadius = Infinity) {
  if (!Array.isArray(entries) || names.length === 0 || !(width > 0) || !(height > 0)) return null;
  const pos = new Map();
  for (const e of entries) {
    if (!e || typeof e !== "object" || typeof e.group !== "string" || pos.has(e.group) || !names.includes(e.group)) continue;
    if (!Number.isInteger(e.col) || typeof e.row !== "number" || !Number.isFinite(e.row) || !Number.isInteger(e.row * 2)) continue;
    if (Math.abs(e.col) > 100 || Math.abs(e.row) > 100) continue;
    pos.set(e.group, { x: e.col * 1.5, y: e.row * SQRT3 });
  }
  if (!names.every((name) => pos.has(name))) return null;
  const units = names.map((name) => pos.get(name));
  for (let i = 0; i < units.length; i++) {
    for (let j = i + 1; j < units.length; j++) {
      if (Math.hypot(units[i].x - units[j].x, units[i].y - units[j].y) < SQRT3 - 1e-6) return null;
    }
  }
  const spanX = Math.max(...units.map((u) => u.x)) - Math.min(...units.map((u) => u.x)) + 2;
  const spanY = Math.max(...units.map((u) => u.y)) - Math.min(...units.map((u) => u.y)) + SQRT3;
  const r = Math.min(width / spanX, height / spanY, maxRadius);
  return centred(units.map((u) => ({ x: u.x * r, y: u.y * r })), names.map((_, i) => i), r, width, height);
}

function blockSide(k, lines) {
  const l = typeof lines === "number" && lines > 0 ? lines : 0;
  return Math.min(MAX_SIDE, Math.max(MIN_SIDE, k * Math.sqrt(l)));
}

// The shared k: the busiest group's sum(side^2) is FILL of the hexagon area (see the top of the file).
function blockScale(linesPerGroup) {
  const target = FILL * HEX_AREA;
  const busiest = (k) => {
    let most = 0;
    for (const lines of linesPerGroup) {
      let area = 0;
      for (let i = 0; i < lines.length; i++) { const s = blockSide(k, lines[i]); area += s * s; }
      if (area > most) most = area;
    }
    return most;
  };
  if (busiest(0) >= target) return 0;
  let lo = 0;
  let hi = 1e-3;
  while (busiest(hi) < target) {
    hi *= 2;
    if (hi > 1e3) return hi;          // too few commits to fill anything: every block is a slab
  }
  for (let it = 0; it < 50; it++) {
    const mid = (lo + hi) / 2;
    if (busiest(mid) < target) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

// Packs one group's blocks (sides in landing order). Returns typed arrays of left x and bottom y.
function packGroup(sides, gi) {
  const n = sides.length;
  const xs = new Float32Array(n);
  const ys = new Float32Array(n);
  const sky = new Float32Array(CELLS).fill(INSET);
  const top = HEX_H - INSET;
  const restOn = (left, s) => {
    const a = Math.max(0, Math.floor(left * CELLS));
    const b = Math.min(CELLS - 1, Math.max(a, Math.ceil((left + s) * CELLS) - 1));
    let m = INSET;
    for (let c = a; c <= b; c++) if (sky[c] > m) m = sky[c];
    return m;
  };
  const clampLeft = (left, s, y) => {
    const hw = Math.min(hexHalfWidth(y), hexHalfWidth(Math.min(y + s, HEX_H))) - INSET;
    const lo = 0.5 - hw;
    const hi = 0.5 + hw - s;
    return hi <= lo ? 0.5 - s / 2 : Math.min(Math.max(left, lo), hi);
  };
  const land = (left, s) => {
    let y = INSET;
    for (let it = 0; it < 4; it++) {
      y = Math.min(restOn(left, s), top - s);
      const next = clampLeft(left, s, y);
      if (Math.abs(next - left) < 1e-7) break;
      left = next;
    }
    y = Math.min(restOn(left, s), top - s);
    return { left: clampLeft(left, s, y), y };
  };
  for (let i = 0; i < n; i++) {
    const s = sides[i];
    let best = null;
    for (let t = 0; t < TRIES; t++) {
      const spot = land(INSET + hash01(gi, i, t) * (1 - 2 * INSET - s), s);
      if (!best || spot.y < best.y - 1e-7) best = spot;
    }
    xs[i] = best.left;
    ys[i] = best.y;
    const a = Math.max(0, Math.floor(best.left * CELLS));
    const b = Math.min(CELLS - 1, Math.max(a, Math.ceil((best.left + s) * CELLS) - 1));
    for (let c = a; c <= b; c++) if (sky[c] < best.y + s) sky[c] = best.y + s;
  }
  return { x: xs, y: ys };
}

// Scene time split: a lead-in before the first landing, the year, then a hold on the full piles.
function timingPlan(duration) {
  const d = typeof duration === "number" && duration > 0 ? duration : 30;
  const lead = Math.min(2.5, d * 0.1);
  const hold = Math.min(4, d * 0.15);
  return { lead, hold, play: Math.max(0.1, d - lead - hold), duration: d };
}

// One segment per calendar month touched by the window: {label: "Jan", from, to} in days from start.
function monthSegments(start, days, formatMonth) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(start));
  if (!m || !(days > 0)) return [];
  const y0 = +m[1];
  const m0 = +m[2] - 1;
  const t0 = Date.UTC(y0, m0, +m[3]);
  const out = [];
  for (let k = 0; k < 120; k++) {
    const from = Math.max(0, Math.round((Date.UTC(y0, m0 + k, 1) - t0) / 86400000));
    if (from >= days) break;
    const to = Math.min(days, Math.round((Date.UTC(y0, m0 + k + 1, 1) - t0) / 86400000));
    const date = new Date(Date.UTC(y0, m0 + k, 1));
    const iso = date.getUTCFullYear() + "-" + String(date.getUTCMonth() + 1).padStart(2, "0");
    const name = typeof formatMonth === "function" ? String(formatMonth(iso)) : iso;
    out.push({ label: name.slice(0, 3), from, to });
  }
  return out;
}

// First index whose value is > t in an ascending array.
function upperBound(arr, t) {
  let lo = 0;
  let hi = arr.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (arr[mid] <= t) lo = mid + 1; else hi = mid;
  }
  return lo;
}

// Height of a falling block's bottom at fall progress u (0..1): accelerates down, then a small bounce.
function fallY(u, from, to, side) {
  const hit = 0.72;
  if (u <= 0) return from;
  if (u < hit) { const v = u / hit; return from + (to - from) * v * v; }
  if (u >= 1) return to;
  const v = (u - hit) / (1 - hit);
  return to + Math.min(0.5 * side, 0.025) * Math.sin(Math.PI * v) * (1 - v);
}

// Everything the draw loop needs, computed once: per group typed arrays in landing order.
function prepare(groups, win, duration) {
  const days = win && typeof win.days === "number" && win.days > 0 ? win.days : 365;
  const plan = timingPlan(duration);
  const lists = groups.map((g) => {
    const raw = Array.isArray(g.commits) ? g.commits : [];
    return raw
      .map((c, i) => ({ day: Array.isArray(c) && typeof c[0] === "number" ? c[0] : NaN, lines: Array.isArray(c) ? Number(c[1]) : 0, i }))
      .filter((c) => Number.isFinite(c.day))
      .map((c) => ({ day: Math.min(Math.max(Math.floor(c.day), 0), days - 1), lines: Number.isFinite(c.lines) && c.lines > 0 ? c.lines : 0, i: c.i }))
      .sort((a, b) => a.day - b.day || a.i - b.i);
  });
  const k = blockScale(lists.map((list) => list.map((c) => c.lines)));

  // The biggest commits (top 0.5%, at least 3) get a flash ring and a hexagon pulse when they land.
  const all = [];
  lists.forEach((list, g) => list.forEach((c, i) => { if (c.lines > 0) all.push([c.lines, g, i]); }));
  all.sort((a, b) => b[0] - a[0] || a[1] - b[1] || a[2] - b[2]);
  const bigCount = Math.min(all.length, Math.max(3, Math.ceil(all.length * 0.005)));
  const bigs = lists.map(() => []);
  all.slice(0, bigCount).forEach(([, g, i]) => bigs[g].push(i));

  const prepared = lists.map((list, g) => {
    const n = list.length;
    const land = new Float64Array(n);
    const side = new Float32Array(n);
    const alpha = new Float32Array(n);
    let i = 0;
    while (i < n) {
      let j = i;
      while (j < n && list[j].day === list[i].day) j++;
      for (let q = i; q < j; q++) {
        const dayf = list[q].day + (q - i + 0.5) / (j - i);
        land[q] = plan.lead + (dayf / days) * plan.play;
      }
      i = j;
    }
    for (let q = 0; q < n; q++) {
      side[q] = blockSide(k, list[q].lines);
      alpha[q] = 0.62 + 0.38 * hash01(g, q, 7);
    }
    const packed = packGroup(side, g);
    const big = bigs[g].sort((a, b) => a - b);
    return { n, land, side, alpha, x: packed.x, y: packed.y, big, bigLand: big.map((q) => land[q]) };
  });
  return { k, days, plan, groups: prepared };
}

function hexPath(g, cx, cy, r) {
  g.beginPath();
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 3) * i;
    const x = cx + r * Math.cos(a);
    const y = cy + r * Math.sin(a);
    if (i === 0) g.moveTo(x, y); else g.lineTo(x, y);
  }
  g.closePath();
}

const clamp01 = (v) => Math.min(Math.max(v, 0), 1);

export default {
  render(ctx) {
    const { container, data, params, partial, gsap, presets } = ctx;
    const tl = gsap.timeline();
    const rawGroups = presets.lookup(data, params.groups);
    const groups = (Array.isArray(rawGroups) ? rawGroups : []).filter((g) => g && typeof g === "object");
    const win = presets.lookup(data, params.window) || {};
    const model = prepare(groups, win, ctx.duration);
    const { plan } = model;
    const el = (tag, className, text) => {
      const node = document.createElement(tag);
      node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    };

    const wrap = el("div", "tw-cap");
    const heading = el("div", "tw-cap-heading", typeof params.heading === "string" ? params.heading : "");
    wrap.append(heading);
    const top = [heading];
    // An optional one-line note under the heading. It is a normal flex child, so the stage (and with it the
    // honeycomb, which is laid out from the stage's measured size) simply gets the remaining height.
    if (typeof params.note === "string" && params.note !== "") {
      const note = el("div", "tw-cap-note", params.note);
      wrap.append(note);
      top.push(note);
    }
    if (Array.isArray(partial) && typeof params.groups === "string" && presets.isPartial(partial, params.groups)) {
      const note = el("div", "tw-cap-partial", "partial data");
      wrap.append(note);
      top.push(note);
    }

    // Legend: only the categories present.
    const present = CATEGORIES.filter((c) => groups.some((g) => categoryOf(g) === c));
    let legend = null;
    if (present.length > 0) {
      legend = el("div", "tw-cap-legend");
      present.forEach((c) => {
        const key = el("div", "tw-cap-key");
        key.append(el("span", "tw-cap-swatch tw-cap-swatch-" + c), el("span", "tw-cap-key-text", CATEGORY_NAMES[c]));
        legend.append(key);
      });
      wrap.append(legend);
    }

    const stage = el("div", "tw-cap-stage");
    const canvas = el("canvas", "tw-cap-canvas");
    stage.append(canvas);
    const labels = groups.map((g) => {
      const label = el("div", "tw-cap-label tw-cap-label-" + categoryOf(g));
      const name = el("div", "tw-cap-name", typeof g.label === "string" && g.label !== "" ? g.label : String(g.name));
      const count = el("div", "tw-cap-count", presets.format(0));
      label.append(name, count);
      stage.append(label);
      return { label, name, count, shown: 0 };
    });
    wrap.append(stage);

    // Month progress bar along the bottom.
    const segments = monthSegments(win.start, model.days, presets.formatMonth);
    const months = el("div", "tw-cap-months");
    const row = el("div", "tw-cap-month-row");
    const monthEls = segments.map((s) => {
      const m = el("div", "tw-cap-month", s.label);
      m.style.flex = String(s.to - s.from);
      row.append(m);
      return m;
    });
    const track = el("div", "tw-cap-month-track");
    const fill = el("div", "tw-cap-month-fill");
    track.append(fill);
    months.append(row, track);
    wrap.append(months);
    container.append(wrap);

    // Colours come from the theme tokens; a block's brightness varies through its alpha.
    const style = typeof getComputedStyle === "function" ? getComputedStyle(container) : null;
    const token = (name) => (style ? style.getPropertyValue(name).trim() : "");
    const fallback = token("--tw-accent") || "gray";
    const colours = {};
    ["core", "extension", "support", "none"].forEach((c) => { colours[c] = token("--tw-cat-" + c) || fallback; });
    const groupColour = groups.map((g) => colours[categoryOf(g)]);

    // Auto layout order: core first (in the middle), then extension, support, the rest; busiest first within.
    const rank = (g) => { const i = CATEGORIES.indexOf(categoryOf(g)); return i < 0 ? CATEGORIES.length : i; };
    const order = groups.map((_, i) => i).sort((a, b) =>
      rank(groups[a]) - rank(groups[b]) || model.groups[b].n - model.groups[a].n || a - b);
    const names = groups.map((g) => String(g.name));

    const g2d = canvas.getContext ? canvas.getContext("2d") : null;
    let layout = { radius: 0, centres: [] };
    let width = 0;
    let height = 0;
    let lastTime = 0;
    let lastMonth = -2;

    function draw(time) {
      lastTime = time;
      const appear = clamp01((time - 0.2) / 0.8);
      // Counters and the month bar (DOM), touched only when they change.
      model.groups.forEach((pg, gi) => {
        const landed = upperBound(pg.land, time);
        if (landed !== labels[gi].shown) {
          labels[gi].shown = landed;
          labels[gi].count.textContent = presets.format(landed);
        }
      });
      const yearFrac = clamp01((time - plan.lead) / plan.play);
      const dayNow = yearFrac * model.days;
      let current = segments.findIndex((s) => dayNow >= s.from && dayNow < s.to);
      if (time < plan.lead) current = -1;
      else if (current < 0 && segments.length > 0) current = segments.length - 1;
      if (current !== lastMonth) {
        monthEls.forEach((m, i) => { m.className = i === current ? "tw-cap-month tw-cap-month-on" : "tw-cap-month"; });
        lastMonth = current;
      }
      fill.style.width = (yearFrac * 100).toFixed(2) + "%";

      if (!g2d || !(width > 0)) return;
      g2d.setTransform(1, 0, 0, 1, 0, 0);
      g2d.clearRect(0, 0, canvas.width, canvas.height);
      const dpr = canvas.width / width;
      g2d.setTransform(dpr, 0, 0, dpr, 0, 0);
      const R = layout.radius;
      const W = 2 * R;
      model.groups.forEach((pg, gi) => {
        const c = layout.centres[gi];
        if (!c) return;
        const colour = groupColour[gi];
        let pulse = 0;
        for (const t of pg.bigLand) if (time >= t && time < t + PULSE) pulse = Math.max(pulse, 1 - (time - t) / PULSE);
        const ox = c.x - R;
        const oy = c.y + R * SQRT3 / 2;
        g2d.save();
        hexPath(g2d, c.x, c.y, R);
        g2d.fillStyle = colour;
        g2d.globalAlpha = appear * (0.1 + 0.18 * pulse);
        g2d.fill();
        g2d.clip();
        const landed = upperBound(pg.land, time);
        const falling = upperBound(pg.land, time + FALL);
        for (let i = 0; i < landed; i++) {
          const s = Math.max(pg.side[i] * W, MIN_PX);
          g2d.globalAlpha = pg.alpha[i];
          g2d.fillRect(ox + pg.x[i] * W, oy - pg.y[i] * W - s, s, s);
        }
        for (let i = landed; i < falling; i++) {
          const u = 1 - (pg.land[i] - time) / FALL;
          const y = fallY(u, HEX_H, pg.y[i], pg.side[i]);
          const s = Math.max(pg.side[i] * W, MIN_PX);
          g2d.globalAlpha = pg.alpha[i];
          g2d.fillRect(ox + pg.x[i] * W, oy - y * W - s, s, s);
        }
        g2d.restore();
        hexPath(g2d, c.x, c.y, R);
        g2d.strokeStyle = colour;
        g2d.globalAlpha = appear * (0.85 + 0.15 * pulse);
        g2d.lineWidth = Math.max(1.2, R * 0.012) + 2.5 * pulse;
        g2d.stroke();
        // Flash rings for the biggest commits.
        pg.big.forEach((i, b) => {
          const age = time - pg.bigLand[b];
          if (age < 0 || age >= FLASH) return;
          const f = age / FLASH;
          const s = pg.side[i] * W;
          g2d.beginPath();
          g2d.arc(ox + pg.x[i] * W + s / 2, oy - pg.y[i] * W - s / 2, s * 0.6 + R * 0.5 * f, 0, Math.PI * 2);
          g2d.strokeStyle = colour;
          g2d.globalAlpha = 1 - f;
          g2d.lineWidth = 3 * (1 - f) + 1;
          g2d.stroke();
        });
      });
      g2d.globalAlpha = 1;
    }

    // Lays out the hexagons for the stage's current size, sizes the canvas and places the labels.
    function fit() {
      const w = stage.clientWidth > 0 ? stage.clientWidth : 1000;
      const h = stage.clientHeight > 0 ? stage.clientHeight : 520;
      const maxRadius = Math.min(w, h) * 0.45;
      layout = overrideLayout(names, params.layout, w, h, maxRadius)
        || honeycombLayout(groups.length, w, h, order, maxRadius);
      width = stage.clientWidth > 0 ? w : 0;
      height = h;
      if (width > 0 && g2d) {
        const dpr = typeof window !== "undefined" && window.devicePixelRatio > 0 ? window.devicePixelRatio : 1;
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
        canvas.style.width = width + "px";
        canvas.style.height = height + "px";
      }
      const R = layout.radius;
      const nameFont = Math.min(18, Math.max(9, R * 0.15));
      const countFont = Math.min(34, Math.max(12, R * 0.26));
      labels.forEach((l, i) => {
        const c = layout.centres[i];
        if (!c) return;
        l.label.style.left = c.x + "px";
        l.label.style.top = c.y - R * 0.74 + "px";
        l.label.style.maxWidth = R * 1.1 + "px";     // the hexagon is 1.15 R wide where the label starts
        // Shrink the name just enough for its longest word to fit the label width (about 0.62 em per letter plus the padding).
        const longest = String(l.name.textContent || "").split(/[\s-]+/).reduce((m, w) => Math.max(m, w.length), 1);
        const fitFont = (R * 1.1) / (longest * 0.62 + 0.8);
        l.name.style.fontSize = Math.max(7, Math.min(nameFont, fitFont)).toFixed(1) + "px";
        l.count.style.fontSize = countFont.toFixed(1) + "px";
      });
      draw(lastTime);
    }
    fit();

    if (typeof ResizeObserver === "function") {
      const observer = new ResizeObserver(() => {
        if (container.isConnected === false) { observer.disconnect(); return; }
        fit();
      });
      observer.observe(stage);
    }

    presets.fadeIn(tl, top, 0, 0.6);
    if (legend) presets.fadeIn(tl, legend, 0.3, 0.6);
    presets.fadeIn(tl, labels.map((l) => l.label), 0.5, 0.6);
    presets.fadeIn(tl, months, 0.8, 0.6);
    // One tween drives the whole animation; draw() depends only on the time, so seeking is exact.
    const clock = { t: 0 };
    tl.to(clock, { t: 1, duration: plan.duration, ease: "none", onUpdate: () => draw(clock.t * plan.duration) }, 0);
    return tl;
  },
  honeycombLayout,
  overrideLayout,
  blockScale,
  blockSide,
  packGroup,
  hexHalfWidth,
  timingPlan,
  monthSegments,
  prepare,
  fallY,
  upperBound,
  constants: { HEX_H, HEX_AREA, FILL, MIN_SIDE, MAX_SIDE, INSET, FALL },
};
