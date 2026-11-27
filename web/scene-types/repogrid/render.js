export default {
  render(ctx) {
    const { container, data, params, gsap, presets } = ctx;
    const tl = gsap.timeline();

    const total = presets.lookup(data, params.value);
    const rows = presets.lookup(data, params.names);
    const names = (Array.isArray(rows) ? rows : []).map((row) => (typeof row === "string" ? row : row.name));

    const wrap = document.createElement("div");
    wrap.className = "tw-repos";

    // Heading: "Across <count> repositories", with the count in its own element so it can be highlighted.
    const template = total === 1 && params.heading_one ? params.heading_one : params.heading;
    const marker = "{count}";
    const at = template.indexOf(marker);
    const textSpan = (value) => {
      const span = document.createElement("span");
      span.className = "tw-repos-text";
      span.textContent = value;
      return span;
    };
    const heading = document.createElement("div");
    heading.className = "tw-repos-heading";
    const count = document.createElement("span");
    count.className = "tw-repos-count";
    heading.append(textSpan(at < 0 ? template : template.slice(0, at)));
    if (at >= 0) {
      heading.append(count);
      heading.append(textSpan(template.slice(at + marker.length)));
    }
    if (typeof total === "number") {
      presets.countUp(tl, count, total, 0.4, 2.0);
    } else {
      count.textContent = "–";
    }
    wrap.append(heading);
    presets.fadeIn(tl, heading, 0, 0.6);

    // Folders: one per repository, bubbling in and settling into the grid.
    if (names.length > 0) {
      const sizeClass = names.length <= 12 ? "lg" : names.length <= 30 ? "md" : "sm";
      const grid = document.createElement("div");
      grid.className = "tw-folders tw-folders-" + sizeClass;
      const folders = names.map((name) => {
        const folder = document.createElement("div");
        folder.className = "tw-folder";
        folder.title = name;
        const body = document.createElement("div");
        body.className = "tw-folder-body";
        const label = document.createElement("span");
        label.className = "tw-folder-name";
        label.textContent = name;
        body.append(label);
        folder.append(body);
        grid.append(folder);
        return folder;
      });
      wrap.append(grid);
      // Cap the stagger so large teams do not overrun the scene.
      presets.bubbleIn(tl, folders, 0.6, Math.min(0.12, 2.5 / folders.length));
    }

    container.append(wrap);
    return tl;
  },
};
