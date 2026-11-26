(function () {
  "use strict";

  const TW = window.TeamWrapped;
  const gsap = window.gsap;
  const timing = TW.timing;
  const payload = JSON.parse(document.getElementById("tw-data").textContent);
  const scenes = payload.scenes;
  const durations = scenes.map((s) => s.duration);
  const music = payload.script.music;
  const MUTE_KEY = "tw-muted";
  const FADE = 0.4;

  const $ = (id) => document.getElementById(id);
  const els = {
    stage: $("tw-stage"), start: $("tw-start"), end: $("tw-end"),
    playBtn: $("tw-play-btn"), replayBtn: $("tw-replay-btn"),
    toggle: $("tw-toggle"), progress: $("tw-progress"),
    mute: $("tw-mute"), sceneTitle: $("tw-scene-title"),
  };

  const state = { started: false, playing: false, index: 0, tl: null, el: null, scrubbing: false };

  function store(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(key);
      localStorage.setItem(key, value);
    } catch (e) { /* storage can be blocked on file:// in some browsers */ }
    return null;
  }

  // ---- music ---------------------------------------------------------
  let audio = null;
  if (music) {
    audio = new Audio(music.src);
    audio.loop = music.loop !== false;
    audio.volume = 0;
    audio.muted = store(MUTE_KEY) === "1";
  } else {
    els.mute.hidden = true;
  }

  function playAudio() {
    if (!audio) return;
    audio.play().catch(() => {});
    gsap.to(audio, { volume: music.volume != null ? music.volume : 0.5, duration: 2, overwrite: true });
  }
  function pauseAudio() { if (audio) audio.pause(); }
  function toggleMute() {
    if (!audio) return;
    audio.muted = !audio.muted;
    store(MUTE_KEY, audio.muted ? "1" : "0");
    refresh();
  }

  // ---- progress line -------------------------------------------------
  const segs = scenes.map((scene, i) => {
    const seg = document.createElement("button");
    seg.type = "button";
    seg.className = "tw-seg";
    seg.dataset.index = String(i);
    seg.style.flex = String(scene.duration);
    seg.title = scene.title;
    seg.setAttribute("aria-label", scene.title);
    const fill = document.createElement("div");
    fill.className = "tw-seg-fill";
    seg.append(fill);
    els.progress.append(seg);
    return { seg, fill };
  });

  function refresh() {
    els.toggle.textContent = state.playing ? "Pause" : "Play";
    if (audio) els.mute.textContent = audio.muted ? "Unmute" : "Mute";
    els.sceneTitle.textContent = scenes[state.index] ? scenes[state.index].title : "";
    segs.forEach((s, i) => s.seg.classList.toggle("tw-current", i === state.index));
  }

  gsap.ticker.add(() => {
    if (!state.started || !state.tl) return;
    const progress = state.tl.progress();
    segs.forEach((s, i) => {
      const pct = i < state.index ? 100 : i === state.index ? progress * 100 : 0;
      s.fill.style.width = pct + "%";
    });
  });

  // ---- scenes --------------------------------------------------------
  function enter(index, play) {
    els.end.hidden = true;
    if (state.tl) state.tl.kill();
    const old = state.el;

    const scene = scenes[index];
    const renderer = TW.sceneTypes[scene.type];
    const el = document.createElement("section");
    el.className = "tw-scene";
    els.stage.append(el);

    const inner = renderer.render({
      container: el, data: scene.data, params: scene.params, duration: scene.duration,
      partial: scene.partial, scope: scene.scope, period: payload.script.period,
      gsap, presets: TW.presets,
    });

    // Pad the scene to exactly its duration so progress and hold time are predictable.
    const tl = gsap.timeline({
      paused: true,
      onComplete: () => (index < scenes.length - 1 ? enter(index + 1, true) : finish()),
    });
    tl.add(inner, 0);
    tl.to({}, { duration: scene.duration }, 0);

    state.index = index;
    state.tl = tl;
    state.el = el;
    state.playing = !!play;

    // Cross-fade between scenes (the only transition implemented so far).
    gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: FADE });
    if (old) gsap.to(old, { opacity: 0, duration: FADE, onComplete: () => old.remove() });

    if (play) tl.play();
    refresh();
  }

  function finish() {
    state.playing = false;
    pauseAudio();
    els.end.hidden = false;
    refresh();
  }

  function setPlaying(playing) {
    if (!state.tl) return;
    state.playing = playing;
    if (playing) { state.tl.play(); playAudio(); } else { state.tl.pause(); pauseAudio(); }
    refresh();
  }

  function start() {
    state.started = true;
    document.body.classList.add("tw-started");
    els.start.hidden = true;
    enter(0, true);
    playAudio();
  }

  // ---- events --------------------------------------------------------
  els.playBtn.addEventListener("click", start);
  function replay() { enter(0, true); playAudio(); }
  els.replayBtn.addEventListener("click", replay);
  els.toggle.addEventListener("click", (ev) => {
    setPlaying(!state.playing);
    if (ev.detail > 0) els.toggle.blur();
  });
  els.mute.addEventListener("click", (ev) => {
    toggleMute();
    if (ev.detail > 0) els.mute.blur();
  });

  function scrubTo(ev) {
    const rect = segs[state.index].seg.getBoundingClientRect();
    const f = Math.min(Math.max((ev.clientX - rect.left) / rect.width, 0), 1);
    state.tl.progress(Math.min(f, 0.999));
  }

  els.progress.addEventListener("pointerdown", (ev) => {
    const seg = ev.target.closest(".tw-seg");
    if (!seg || !state.started) return;
    const i = Number(seg.dataset.index);
    if (i === state.index && els.end.hidden) {
      state.scrubbing = true;
      els.progress.setPointerCapture(ev.pointerId);
      scrubTo(ev);
    } else {
      enter(i, state.playing);
    }
  });
  els.progress.addEventListener("pointermove", (ev) => { if (state.scrubbing) scrubTo(ev); });
  els.progress.addEventListener("pointerup", () => { state.scrubbing = false; });

  document.addEventListener("keydown", (ev) => {
    if (!state.started) return;
    if (ev.code === "Space") {
      if (ev.target instanceof HTMLButtonElement) return;
      ev.preventDefault();
      if (!els.end.hidden) replay();
      else setPlaying(!state.playing);
    }
    else if (ev.code === "ArrowRight") enter(Math.min(state.index + 1, scenes.length - 1), state.playing);
    else if (ev.code === "ArrowLeft") enter(Math.max(state.index - 1, 0), state.playing);
    else if (ev.key === "m" || ev.key === "M") toggleMute();
  });

  TW.player = { state, scenes, durations, enter, setPlaying };
  refresh();
})();
