export default {
  render(ctx) {
    const { container, data, params, gsap, presets } = ctx;
    const people = (data.contributors && data.contributors.list) || [];
    const tl = gsap.timeline();

    // A stage with nobody in it is skipped, so no bots means no robot stage; a team of none still shows the first heading.
    const all = (Array.isArray(params.stages) ? params.stages : []).map((stage) => ({
      heading: String(stage.heading),
      names: stage.names === true,     // a name label under each avatar (people without a `name` get none)
      members: people.filter((p) => (stage.kinds || []).includes(p.kind)),
    }));
    const stages = all.filter((s) => s.members.length > 0);
    if (stages.length === 0 && all.length > 0) stages.push(all[0]);

    const BAND = 48;           // height of the heading that introduces each later stage
    const HOLD = 3.5;          // time to find yourself before the next stage starts

    const wrap = document.createElement("div");
    wrap.className = "tw-cast";
    const arena = document.createElement("div");
    arena.className = "tw-cast-arena";

    // "{count:contributor|contributors}" -> text before the number, and the text after it (with the right word).
    const TOKEN = /\{count(?::([^|}]*)\|([^}]*))?\}/;
    const makeHeading = (stage, className) => {
      const n = stage.members.length;
      const heading = document.createElement("div");
      heading.className = className;
      const m = TOKEN.exec(stage.heading);
      const text = (value) => {
        const span = document.createElement("span");
        span.className = "tw-cast-text";
        span.textContent = value;
        return span;
      };
      const count = document.createElement("span");
      count.className = "tw-cast-count";
      if (m) {
        const word = m[1] === undefined ? "" : " " + (n === 1 ? m[1] : m[2]);
        heading.append(text(stage.heading.slice(0, m.index)), count, text(word + stage.heading.slice(m.index + m[0].length)));
      } else {
        heading.append(text(stage.heading));
      }
      if (typeof heading.setAttribute === "function") {
        heading.setAttribute("aria-label", presets.fillTemplate(stage.heading, { count: n }));
      }
      return { heading, count, n };
    };

    const first = stages.length > 0 ? makeHeading(stages[0], "tw-cast-heading") : null;
    if (first) wrap.append(first.heading);
    wrap.append(arena);
    container.append(wrap);

    // The arena is measured once it is in the page; a stub without a layout gets a plain size.
    const W = arena.clientWidth > 0 ? arena.clientWidth : 1000;
    const H = arena.clientHeight > 0 ? arena.clientHeight : 520;

    // Where each stage's avatars sit once stages 0..k are on screen: the space is shared by headcount
    // (never less than a quarter each, so a few robots still get a visible row), with a heading band before each later stage.
    const total = stages.reduce((sum, s) => sum + s.members.length, 0);
    const layoutAt = (k) => {
      const weights = stages.slice(0, k + 1).map((s) => Math.max(s.members.length, total * 0.25));
      const weightSum = weights.reduce((a, b) => a + b, 0);
      const free = H - k * BAND;
      let top = 0;
      return weights.map((weight, i) => {
        if (i > 0) top += BAND;
        const height = (free * weight) / weightSum;
        const layout = presets.scatterLayout(stages[i].members.length, W, height, 120, 20, { labels: stages[i].names });
        const placed = { size: layout.size, label: layout.label, bandTop: top - BAND,
          points: layout.points.map((p) => ({ x: p.x, y: top + p.y })) };
        top += height;
        return placed;
      });
    };
    const layouts = stages.map((_, k) => layoutAt(k));

    // Stage i starts once stage i-1 has landed and the audience has had time to look.
    const DROP = 0.9;
    let at = 0.2;
    stages.forEach((stage, i) => {
      const own = layouts[i][i];
      const n = stage.members.length;
      const each = Math.min(0.08, 2.5 / Math.max(n, 1));    // cap the drop time so large teams do not overrun the scene
      const headingAt = at;

      // Earlier stages and their headings make room: they shrink and shift to where this stage's layout puts them.
      for (let j = 0; j < i; j++) {
        const from = layouts[j][j];
        const to = layouts[i][j];
        tl.to(stages[j].faces, {
          x: (idx) => to.points[idx].x - from.points[idx].x,
          y: (idx) => to.points[idx].y - from.points[idx].y,
          scale: to.size / from.size,
          duration: 1.0, ease: "power2.inOut",
        }, headingAt);
        if (stages[j].labels.length > 0) {
          // Labels hang from their top centre, so they shrink with the avatar and stay just under it.
          const labels = stages[j].labels;
          const lift = (p, layout) => p.y + layout.label.offset;
          tl.to(labels.map((l) => l.el), {
            x: (k) => to.points[labels[k].idx].x - from.points[labels[k].idx].x,
            y: (k) => lift(to.points[labels[k].idx], to) - lift(from.points[labels[k].idx], from),
            scale: to.size / from.size,
            duration: 1.0, ease: "power2.inOut",
          }, headingAt);
        }
        if (j > 0) tl.to(stages[j].title.heading, { y: to.bandTop - from.bandTop, duration: 1.0, ease: "power2.inOut" }, headingAt);
      }

      stage.title = i === 0 ? first : makeHeading(stage, "tw-cast-heading tw-cast-heading-late");
      if (i === 0) {
        presets.fadeIn(tl, stage.title.heading, headingAt, 0.6);
      } else {
        stage.title.heading.style.top = own.bandTop + "px";
        arena.append(stage.title.heading);
        // Rises from below the screen.
        tl.fromTo(stage.title.heading, { opacity: 0, y: H + 300 }, { opacity: 1, y: 0, duration: 0.9, ease: "power3.out" }, headingAt);
      }
      presets.countUp(tl, stage.title.count, n, headingAt + 0.2, 1.2);

      stage.faces = stage.members.map((p, idx) => {
        const img = document.createElement("img");
        img.className = "tw-cast-face";
        img.src = p.avatar_file;
        img.alt = p.login || "contributor without a GitHub account";
        const c = own.points[idx];
        img.style.left = c.x - own.size / 2 + "px";
        img.style.top = c.y - own.size / 2 + "px";
        img.style.width = own.size + "px";
        img.style.height = own.size + "px";
        arena.append(img);
        return img;
      });
      stage.labels = [];
      if (stage.names) {
        const label = own.label;
        stage.members.forEach((p, idx) => {
          if (typeof p.name !== "string" || p.name === "") return;
          const el = document.createElement("div");
          el.className = "tw-cast-name";
          el.textContent = p.name;
          if (typeof el.setAttribute === "function") el.setAttribute("aria-hidden", "true");   // the image alt names them
          const c = own.points[idx];
          el.style.left = c.x - label.width / 2 + "px";
          el.style.top = c.y + label.offset + "px";
          el.style.width = label.width + "px";
          el.style.height = label.height + "px";
          el.style.lineHeight = label.height + "px";
          el.style.fontSize = label.font + "px";
          arena.append(el);
          stage.labels.push({ el, idx });
        });
      }
      const dropAt = headingAt + 0.7;
      const rise = (idx) => own.points[idx].y + 200 + ((idx * 37) % 120);
      presets.dropIn(tl, stage.faces, dropAt, each, rise, DROP);
      if (stage.labels.length > 0) {
        // Each label falls with its avatar, a beat behind it, using the avatar's own place in the stagger.
        const labels = stage.labels;
        tl.fromTo(labels.map((l) => l.el), { opacity: 0, y: (k) => -rise(labels[k].idx) },
          { opacity: 0.8, y: 0, duration: DROP, ease: "bounce.out",
            stagger: (k) => each * labels[k].idx }, dropAt + 0.12);
      }
      at = dropAt + each * Math.max(n - 1, 0) + DROP + HOLD;
    });
    return tl;
  },
};
