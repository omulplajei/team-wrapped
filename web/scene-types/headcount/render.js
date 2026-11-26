export default {
  render(ctx) {
    const { container, data, params, gsap, presets } = ctx;
    const people = (data.contributors && data.contributors.list) || [];
    const tl = gsap.timeline();
    let at = 0.2;

    params.groups.forEach((group) => {
      const members = people.filter((p) => group.kinds.includes(p.kind));

      const section = document.createElement("section");
      section.className = "tw-group";
      const count = document.createElement("div");
      count.className = "tw-group-count";
      const label = document.createElement("div");
      label.className = "tw-group-label";
      label.textContent = group.label;
      const faces = document.createElement("div");
      faces.className = "tw-faces";

      const imgs = members.map((p) => {
        const img = document.createElement("img");
        img.className = "tw-face";
        img.src = p.avatar_file;
        img.alt = p.login || "contributor without a GitHub account";
        faces.append(img);
        return img;
      });

      section.append(count, label, faces);
      container.append(section);

      // Cap the total pop-in time so large teams do not overrun the scene.
      const each = Math.min(0.06, 2 / Math.max(members.length, 1));
      presets.fadeIn(tl, section, at, 0.5);
      presets.countUp(tl, count, members.length, at, 1.0);
      presets.popIn(tl, imgs, at + 0.4, each);
      at += 0.4 + each * members.length + 0.8;
    });

    return tl;
  },
};
