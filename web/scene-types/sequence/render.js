export default {
  render(ctx) {
    const { container, data, params, partial, gsap, presets } = ctx;
    const tl = gsap.timeline();

    const wrap = document.createElement("div");
    wrap.className = "tw-seq";

    const part = (className, text) => {
      const el = document.createElement("div");
      el.className = className;
      el.textContent = text;
      return el;
    };

    const heading = part("tw-seq-heading", params.heading);
    wrap.append(heading);
    presets.fadeIn(tl, heading, 0, 0.6);

    const body = document.createElement("div");
    body.className = "tw-seq-body";
    const steps = Array.isArray(params.steps) ? params.steps : [];

    steps.forEach((step, i) => {
      const at = 0.8 + i * 1.4;

      if (typeof step.text === "string") {
        const text = part("tw-seq-text", step.text);
        body.append(text);
        presets.popIn(tl, [text], at, 0, 0.5);
        return;
      }

      const el = document.createElement("div");
      el.className = "tw-seq-step";
      const lead = typeof step.lead === "string" ? part("tw-seq-lead", step.lead) : null;
      const raw = presets.lookup(data, step.value);
      // Shown at its final value straight away: the swell is the only animation.
      const value = part("tw-seq-value", typeof raw === "number" ? presets.format(raw) : "–");
      const label = part("tw-seq-label", step.label);
      const badge = presets.isPartial(partial, step.value) ? part("tw-seq-partial", "partial data") : null;
      el.append(...[lead, value, label, badge].filter(Boolean));
      body.append(el);

      // The lead text comes first, then the number swells and settles, and the label (with the
      // partial badge, if any) fades in last, once the number is back to size.
      if (lead) presets.fadeIn(tl, lead, at, 0.4);
      const numberAt = at + (lead ? 0.3 : 0);
      presets.swellIn(tl, value, numberAt);
      presets.fadeIn(tl, badge ? [label, badge] : label, numberAt + 0.45, 0.4);
    });

    wrap.append(body);
    container.append(wrap);
    return tl;
  },
};
