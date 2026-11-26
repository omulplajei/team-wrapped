export default {
  render(ctx) {
    const { container, data, params, partial, gsap, presets } = ctx;
    const grid = document.createElement("div");
    grid.className = "tw-stats";
    const cards = [];
    const tl = gsap.timeline();

    params.items.forEach((item, i) => {
      const card = document.createElement("div");
      card.className = "tw-stat";
      const value = document.createElement("div");
      value.className = "tw-stat-value";
      const label = document.createElement("div");
      label.className = "tw-stat-label";
      label.textContent = item.label;
      card.append(value, label);

      const raw = presets.lookup(data, item.value);
      if (typeof raw === "number") {
        presets.countUp(tl, value, raw, 0.3 + i * 0.15, 1.2);
      } else {
        value.textContent = "–";
      }
      if (presets.isPartial(partial, item.value)) {
        const badge = document.createElement("div");
        badge.className = "tw-stat-partial";
        badge.textContent = "partial data";
        card.append(badge);
      }
      grid.append(card);
      cards.push(card);
    });

    container.append(grid);
    presets.stagger(tl, cards, 0, 0.15, 0.5);
    return tl;
  },
};
