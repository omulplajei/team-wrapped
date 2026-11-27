export default {
  render(ctx) {
    const { container, data, params, partial, gsap, presets } = ctx;
    const tl = gsap.timeline();

    const wrap = document.createElement("div");
    wrap.className = "tw-hero";
    // Optional line above the number. Everything else starts a little later so it can be read first.
    const hasHeading = typeof params.heading === "string" && params.heading !== "";
    if (hasHeading) {
      const heading = document.createElement("div");
      heading.className = "tw-hero-heading";
      heading.textContent = params.heading;
      wrap.append(heading);
    }
    const delay = hasHeading ? 0.7 : 0;
    const value = document.createElement("div");
    value.className = "tw-hero-value";
    const label = document.createElement("div");
    label.className = "tw-hero-label";
    label.textContent = params.label;
    wrap.append(value, label);

    // Optional shaping of the hero count-up (for example a dramatic expo.out); invalid values fall back to the defaults.
    const countDuration = typeof params.count_duration === "number" && params.count_duration > 0 ? params.count_duration : 2.5;
    const countEase = typeof params.count_ease === "string" && params.count_ease !== "" ? params.count_ease : "power1.out";
    const hero = presets.lookup(data, params.value);
    if (typeof hero === "number") {
      presets.countUp(tl, value, hero, 0.3 + delay, countDuration, countEase);
    } else {
      value.textContent = "–";
    }
    if (presets.isPartial(partial, params.value)) {
      const badge = document.createElement("div");
      badge.className = "tw-hero-partial";
      badge.textContent = "partial data";
      wrap.append(badge);
    }

    const supporting = Array.isArray(params.supporting) ? params.supporting : [];
    if (supporting.length > 0) {
      const row = document.createElement("div");
      row.className = "tw-hero-supporting";
      const cards = [];
      supporting.forEach((item, i) => {
        const card = document.createElement("div");
        card.className = "tw-hero-sub";
        const subValue = document.createElement("div");
        subValue.className = "tw-hero-sub-value";
        const subLabel = document.createElement("div");
        subLabel.className = "tw-hero-sub-label";
        subLabel.textContent = item.label;
        card.append(subValue, subLabel);

        const raw = presets.lookup(data, item.value);
        if (typeof raw === "number") {
          presets.countUp(tl, subValue, raw, 2.8 + delay + i * 0.2, 1.0);
        } else {
          subValue.textContent = "–";
        }
        if (presets.isPartial(partial, item.value)) {
          const subBadge = document.createElement("div");
          subBadge.className = "tw-hero-sub-partial";
          subBadge.textContent = "partial data";
          card.append(subBadge);
        }
        row.append(card);
        cards.push(card);
      });
      wrap.append(row);
      presets.popIn(tl, cards, 2.8 + delay, 0.2);
    }

    container.append(wrap);
    presets.fadeIn(tl, wrap, 0, 0.6);
    return tl;
  },
};
