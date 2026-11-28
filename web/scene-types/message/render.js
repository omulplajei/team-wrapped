// message: a heading, optionally a smaller line under it (`subtext`) and a theme logo above it (`logo`, the
// logo's name in the theme's `logos`). A logo the theme does not define is simply left out.
export default {
  render(ctx) {
    const { container, params, gsap, presets } = ctx;
    const tl = gsap.timeline();
    const heading = document.createElement("h1");
    heading.className = "tw-message";
    heading.textContent = params.text;

    const logos = ctx.theme && ctx.theme.logos;
    const src = typeof params.logo === "string" && logos && Object.prototype.hasOwnProperty.call(logos, params.logo)
      ? logos[params.logo] : null;
    const subtext = typeof params.subtext === "string" && params.subtext !== "" ? params.subtext : null;
    if (!src && !subtext) {
      container.appendChild(heading);
      presets.fadeIn(tl, heading, 0.2, 0.8);
      return tl;
    }

    const wrap = document.createElement("div");
    wrap.className = "tw-message-scene";
    let at = 0.2;
    if (src) {
      const logo = document.createElement("img");
      logo.className = "tw-message-logo";
      logo.setAttribute("src", src);
      logo.setAttribute("alt", "");
      wrap.append(logo);
      presets.swellIn(tl, logo, at, 1.12, 0.9);
      at += 0.8;
    }
    wrap.append(heading);
    presets.fadeIn(tl, heading, at, 0.8);
    if (subtext) {
      const sub = document.createElement("p");
      sub.className = "tw-message-sub";
      sub.textContent = subtext;
      wrap.append(sub);
      presets.fadeIn(tl, sub, at + 0.7, 0.8);
    }
    container.appendChild(wrap);
    return tl;
  },
};
