export default {
  render(ctx) {
    const { container, params, gsap, presets } = ctx;
    const heading = document.createElement("h1");
    heading.className = "tw-message";
    heading.textContent = params.text;
    container.appendChild(heading);
    const tl = gsap.timeline();
    presets.fadeIn(tl, heading, 0.2, 0.8);
    return tl;
  },
};
