export default {
  render(ctx) {
    const { container, data, params, partial, gsap, presets } = ctx;
    const tl = gsap.timeline();

    const wrap = document.createElement("div");
    wrap.className = "tw-seq";

    const heading = document.createElement("div");
    heading.className = "tw-seq-heading";
    heading.textContent = params.heading;
    wrap.append(heading);
    presets.fadeIn(tl, heading, 0, 0.6);

    const body = document.createElement("div");
    body.className = "tw-seq-body";
    const steps = Array.isArray(params.steps) ? params.steps : [];

    steps.forEach((step, i) => {
      let el;
      if (typeof step.text === "string") {
        el = document.createElement("div");
        el.className = "tw-seq-text";
        el.textContent = step.text;
      } else {
        el = document.createElement("div");
        el.className = "tw-seq-step";
        const value = document.createElement("div");
        value.className = "tw-seq-value";
        const raw = presets.lookup(data, step.value);
        // Shown at its final value straight away: the pop is the only animation.
        value.textContent = typeof raw === "number" ? presets.format(raw) : "–";
        const label = document.createElement("div");
        label.className = "tw-seq-label";
        label.textContent = step.label;
        el.append(value, label);
        if (presets.isPartial(partial, step.value)) {
          const badge = document.createElement("div");
          badge.className = "tw-seq-partial";
          badge.textContent = "partial data";
          el.append(badge);
        }
      }
      body.append(el);
      presets.popIn(tl, [el], 0.8 + i * 1.0, 0, 0.5);
    });

    wrap.append(body);
    container.append(wrap);
    return tl;
  },
};
