export default {
  render(ctx) {
    const { container, data, params, partial, gsap, presets } = ctx;
    const tl = gsap.timeline();

    const list = presets.lookup(data, params.records);
    const first = Array.isArray(list) && list.length > 0 ? list[0] : null;
    const record = first !== null && typeof first === "object" ? first : null;
    const valueKey = typeof params.value_key === "string" && params.value_key !== "" ? params.value_key : "value";

    const part = (className, text) => {
      const el = document.createElement("div");
      el.className = className;
      el.textContent = text;
      return el;
    };

    const raw = record ? record[valueKey] : undefined;
    const teaser = part("tw-cur-teaser", params.teaser);
    // Shown at its final value straight away: the swell is the only animation.
    const value = part("tw-cur-value", typeof raw === "number" ? presets.format(raw) : "–");
    const unit = part("tw-cur-unit", params.unit);
    const badge = presets.isPartial(partial, params.records) ? part("tw-cur-partial", "partial data") : null;
    const hasContext = typeof params.context === "string" && params.context !== "";
    const context = hasContext ? part("tw-cur-context", record ? presets.fillTemplate(params.context, record) : "") : null;

    const wrap = document.createElement("div");
    wrap.className = "tw-cur";
    wrap.append(...[teaser, value, unit, badge, context].filter(Boolean));
    container.append(wrap);

    presets.fadeIn(tl, teaser, 0, 0.6);
    presets.swellIn(tl, value, 0.9);
    presets.fadeIn(tl, badge ? [unit, badge] : unit, 1.35, 0.4);
    if (context) presets.fadeIn(tl, context, 1.85, 0.5);
    return tl;
  },
};
