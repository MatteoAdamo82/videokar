// The clock: playing, seeking, looping a line, and the frame loop that lights
// up words as they are sung.
import {$, audio, scroll, wave, head, fmt, say} from "./dom.js";
import {S, loopBounds} from "./store.js";

export function seek(t, {centre = false} = {}) {
  audio.currentTime = Math.max(0, t);
  // Moving the clock without moving the view looks like nothing happened, which
  // is exactly how clicking a line used to feel while paused.
  const x = audio.currentTime * S.pps;
  if (centre || x < scroll.scrollLeft + 40 || x > scroll.scrollLeft + scroll.clientWidth - 40) {
    scroll.scrollLeft = Math.max(0, x - scroll.clientWidth / 3);
  }
  tick();
}

export function drawLoop() {
  const bounds = loopBounds();
  const band = $("#loopband");
  if (!bounds) { band.style.display = "none"; return; }
  band.style.display = "block";
  band.style.left = bounds[0] * S.pps + "px";
  band.style.width = (bounds[1] - bounds[0]) * S.pps + "px";
}

export function setRate(rate) {
  audio.playbackRate = rate;
  // Pitch correction is the point: half speed an octave down is harder to
  // place a word in, not easier. The prefixed names are for older engines.
  for (const key of ["preservesPitch", "mozPreservesPitch", "webkitPreservesPitch"]) {
    if (key in audio) audio[key] = true;
  }
  $("#speed").value = String(rate);
}

export const RATES = [0.25, 0.5, 0.75, 1];

export function stepRate(direction) {
  const at = RATES.indexOf(audio.playbackRate);
  const next = at < 0 ? RATES.length - 1
    : Math.min(RATES.length - 1, Math.max(0, at + direction));
  setRate(RATES[next]);
  say(`speed ${RATES[next]}×`);
}

export function toggleLoop() {
  S.loopOn = !S.loopOn;
  $("#loop").classList.toggle("on", S.loopOn);
  drawLoop();
  const bounds = loopBounds();
  if (S.loopOn && !bounds) {
    say("pick a line first — loop repeats the selected one", "bad");
  } else if (bounds) {
    seek(bounds[0]);
    say(`looping ${S.selected} at ${audio.playbackRate}×`);
  }
}

export function tick() {
  if (!S.doc) { requestAnimationFrame(tick); return; }
  const t = audio.currentTime;
  const bounds = loopBounds();
  // Only the far edge is enforced. Scrubbing to somewhere before the loop is a
  // deliberate act — playback runs into the region and starts repeating there.
  if (bounds && !audio.paused && t >= bounds[1]) audio.currentTime = bounds[0];
  head.style.left = t * S.pps + "px";
  $("#clock").textContent = `${fmt(t)} / ${fmt(S.duration)}`;
  for (const el of document.querySelectorAll(".word")) {
    const word = S.wordIndex.get(el.dataset.word);
    el.classList.toggle("sung", Boolean(word && word.start != null && t >= word.start));
  }
  if (S.follow && !audio.paused) {
    const x = t * S.pps;
    if (x < scroll.scrollLeft + 80 || x > scroll.scrollLeft + scroll.clientWidth - 160) {
      scroll.scrollLeft = x - scroll.clientWidth / 3;
    }
  }
  requestAnimationFrame(tick);
}

export function wireTransport() {
  $("#play").onclick = () => (audio.paused ? audio.play() : audio.pause());
  audio.onplay = () => { S.follow = true; $("#play").textContent = "❚❚ Pause"; };
  audio.onpause = () => { $("#play").textContent = "▶︎ Play"; };
  $("#speed").onchange = () => setRate(parseFloat($("#speed").value));
  $("#loop").onclick = toggleLoop;

  scroll.addEventListener("mousedown", (event) => {
    if (event.target === wave) { S.follow = false; seek(event.offsetX / S.pps); }
  });
  scroll.addEventListener("scroll", () => { if (!audio.paused) S.follow = false; });
}
