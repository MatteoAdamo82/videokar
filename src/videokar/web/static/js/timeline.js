// The timeline: the waveform, the blocks and word chips drawn on it, and every
// way of changing a document by hand — dragging, retyping, pinning, muting.
import {$, audio, scroll, track, linesEl, wave, side, fmt, say, escapeHtml, round} from "./dom.js";
import {S, lines, wordsText} from "./store.js";
import {post, report} from "./api.js";
import {seek, drawLoop} from "./transport.js";

export function layout() {
  const width = Math.max(900, Math.round(S.duration * S.pps));
  track.style.width = width + "px";
  wave.width = width; wave.height = 320;
  wave.style.width = width + "px"; wave.style.height = "320px";
  drawWave();
}

function drawWave() {
  const ctx = wave.getContext("2d");
  ctx.clearRect(0, 0, wave.width, wave.height);
  const mid = 95, half = 78;
  if (S.peaks) {
    const perSecond = S.peaks.buckets_per_second;
    ctx.fillStyle = "#3a3550";
    for (let x = 0; x < wave.width; x++) {
      const t = x / S.pps;
      const from = Math.floor(t * perSecond);
      const to = Math.max(from + 1, Math.floor(((x + 1) / S.pps) * perSecond));
      let peak = 0;
      for (let i = from; i < to && i < S.peaks.peaks.length; i++) peak = Math.max(peak, S.peaks.peaks[i]);
      const h = (peak / 255) * half;
      ctx.fillRect(x, mid - h, 1, h * 2);
    }
  }
  // Vocal regions: where the stem says someone is singing.
  ctx.fillStyle = "#6fd08c22";
  for (const [a, b] of S.doc.song.vocal_regions) ctx.fillRect(a * S.pps, 8, (b - a) * S.pps, 10);
  // A second grid, so a drag has something to read distance against.
  ctx.strokeStyle = "#ffffff10"; ctx.fillStyle = "#6b6683";
  ctx.font = "10px ui-monospace, monospace";
  const step = S.pps < 40 ? 10 : S.pps < 90 ? 5 : 1;
  for (let t = 0; t < S.duration; t += step) {
    const x = Math.round(t * S.pps) + 0.5;
    ctx.beginPath(); ctx.moveTo(x, 24); ctx.lineTo(x, wave.height); ctx.stroke();
    ctx.fillText(fmt(t).slice(0, -3), x + 3, 34);
  }
}

function toolButton(label, onClick) {
  const b = document.createElement("button");
  b.textContent = label;
  b.onmousedown = (e) => e.stopPropagation();
  b.onclick = (e) => { e.stopPropagation(); onClick(); };
  return b;
}

// How far a line's start sits from the nearest vocal attack, phrased as a
// direction to drag it rather than merely "something is wrong".
const offBy = (line) => (S.doc.off_the_attack || {})[line.id];

function sideRow(line) {
  const row = document.createElement("div");
  row.className = "row"
    + (S.doc.suspicious.includes(line.id) ? " flagged" : "")
    + (line.sung ? "" : " muted")
    + (S.selected === line.id ? " active" : "");
  row.dataset.line = line.id;
  if (line.flags.includes("off_the_attack")) {
    const off = offBy(line);
    row.title = `starts ${off > 0 ? "after" : "before"} the voice comes in, by ${Math.abs(off).toFixed(2)}s`;
  }
  row.innerHTML = `<span class="id">${line.id}</span><span class="txt">${escapeHtml(wordsText(line))}</span>`;
  row.ondblclick = (event) => { event.stopPropagation(); retypeLine(line); };
  row.onclick = () => {
    select(line.id);
    if (line.start != null) seek(line.start - 0.4, {centre: true});
  };
  return row;
}

function lineBlock(line) {
  const block = document.createElement("div");
  block.className = "lineblock"
    + (line.pinned ? " pinned" : "") + (line.sung ? "" : " muted")
    + (S.doc.suspicious.includes(line.id) ? " flagged" : "")
    + (S.selected === line.id ? " sel" : "");
  block.style.left = line.start * S.pps + "px";
  block.style.width = Math.max(26, (line.end - line.start) * S.pps) + "px";
  block.dataset.line = line.id;
  const off = offBy(line);
  const offNote = line.flags.includes("off_the_attack")
    ? ` · ${off > 0 ? "+" : ""}${off.toFixed(2)}s from the attack` : "";
  block.innerHTML = `<span class="label">${line.id} · ${line.start.toFixed(2)}${
    line.flags.length ? " · " + line.flags.join(",") : ""}${offNote}</span>`;
  block.querySelector(".label").ondblclick = (event) => {
    event.stopPropagation();
    retypeLine(line);
  };

  const tools = document.createElement("div");
  tools.className = "tools";
  tools.append(
    toolButton(line.pinned ? "📌 pinned" : "pin", () => edit({op: "pin", line: line.id, value: !line.pinned})),
    toolButton(line.sung ? "mute" : "🔇 muted", () => edit({op: "mute", line: line.id, value: !line.sung})),
  );
  block.append(tools);

  for (const word of line.words) {
    if (word.start == null) continue;
    block.append(wordChip(word, line));
  }
  return block;
}

function wordChip(word, line) {
  const el = document.createElement("div");
  el.className = "word" + (word.manual ? " manual" : "");
  el.style.left = (word.start - line.start) * S.pps + "px";
  el.style.width = Math.max(16, (word.end - word.start) * S.pps) + "px";
  el.textContent = word.text;
  // The chip is as wide as the word is long in time, which at a normal zoom
  // is narrower than the word itself.
  el.title = `${word.text}  ${word.start.toFixed(2)}–${word.end.toFixed(2)}`;
  el.dataset.word = word.id;
  el.ondblclick = (event) => { event.stopPropagation(); retype(el, word); };
  for (const edge of ["l", "r"]) {
    const grip = document.createElement("div");
    grip.className = "grip " + edge;
    grip.dataset.side = edge;
    el.append(grip);
  }
  return el;
}

export function render() {
  linesEl.innerHTML = ""; side.innerHTML = "";
  if (!S.doc) return;
  const heading = document.createElement("h2");
  heading.textContent = "lines";
  side.append(heading);

  for (const line of lines()) {
    side.append(sideRow(line));
    if (line.start != null) linesEl.append(lineBlock(line));
  }
  S.wordIndex = new Map(lines().flatMap((line) => line.words.map((w) => [w.id, w])));
  drawLoop();
}

export function select(id) {
  // Class toggle rather than a re-render: rebuilding the DOM on mousedown
  // detaches the element the double-click is about to land on, so retyping a
  // word never fired.
  S.selected = id;
  for (const block of document.querySelectorAll(".lineblock")) {
    block.classList.toggle("sel", block.dataset.line === id);
  }
  for (const row of document.querySelectorAll("#side .row")) {
    row.classList.toggle("active", row.dataset.line === id);
  }
  drawLoop();
}

export async function edit(body) {
  say("saving…");
  try {
    const result = await post("/api/edit", body);
    S.doc = result;
    S.undoDepth = result.undo_depth ?? S.undoDepth;
    $("#undo").disabled = S.undoDepth === 0;
    render();
    say(result.edit.description + ` · ${S.doc.suspicious.length} still flagged`, "good");
  } catch (err) {
    // A refused drag is information, not a failure: the timeline would have
    // inverted, and the server says which line it collided with.
    report(err);
    render();
  }
}

// A field on the page rather than window.prompt: a browser told to stop showing
// dialogs returns null from those without asking, so the control did nothing.
function typeOver({className, value, box, minWidth, above = false, commit}) {
  document.querySelectorAll("." + className).forEach((old) => old.remove());
  const field = document.createElement("input");
  field.className = className;
  field.value = value;
  Object.assign(field.style, {
    left: Math.max(above ? 8 : 0, box.left) + "px",
    top: (above ? Math.max(60, box.top - 34) : box.top) + "px",
    width: Math.max(minWidth, box.width) + "px",
  });
  document.body.append(field);
  field.focus();
  field.select();

  let done = false;
  const finish = async (keep) => {
    if (done) return;
    done = true;
    const typed = field.value.trim();
    field.remove();
    if (!keep || !typed || typed === value) return;
    await commit(typed);
  };
  field.onblur = () => finish(true);
  field.onkeydown = (event) => {
    event.stopPropagation();
    if (event.key === "Enter") finish(true);
    if (event.key === "Escape") finish(false);
  };
}

function retype(el, word) {
  typeOver({
    className: "wordedit",
    value: word.text,
    box: el.getBoundingClientRect(),
    minWidth: 70,
    commit: (text) => edit({op: "set_text", word: word.id, text}),
  });
}

export function retypeLine(line) {
  const block = linesEl.querySelector(`[data-line="${line.id}"]`);
  typeOver({
    className: "lineedit",
    value: wordsText(line),
    box: block ? block.getBoundingClientRect() : {left: 80, top: 120, width: 460},
    minWidth: 320,
    above: true,
    commit: (text) => edit({op: "set_line_text", line: line.id, text}),
  });
}

export function setZoom(value) {
  const anchor = audio.currentTime;
  // Canvas has a hard width limit; past it the waveform silently stops drawing.
  S.pps = Math.max(12, Math.min(value, 30000 / Math.max(S.duration, 1)));
  layout(); render();
  scroll.scrollLeft = anchor * S.pps - scroll.clientWidth / 2;
}

// ---- dragging -------------------------------------------------------------
let drag = null;

export function wireTimeline() {
  $("#zoomin").onclick = () => setZoom(S.pps * 1.5);
  $("#zoomout").onclick = () => setZoom(S.pps / 1.5);

  linesEl.addEventListener("mousedown", (event) => {
    const wordEl = event.target.closest(".word");
    const blockEl = event.target.closest(".lineblock");
    if (!blockEl) return;
    event.preventDefault();
    const id = blockEl.dataset.line;
    select(id);
    const grip = event.target.closest(".grip");
    const element = wordEl || blockEl;
    drag = {
      kind: grip ? "resize" : wordEl ? "word" : "line",
      side: grip ? grip.dataset.side : null,
      id: wordEl ? wordEl.dataset.word : id,
      element,
      originX: event.clientX,
      startLeft: parseFloat(element.style.left),
      startWidth: element.getBoundingClientRect().width,
      offset: 0,
    };
    if (grip) element.classList.add("resizing");
  });

  window.addEventListener("mousemove", (event) => {
    if (!drag) return;
    drag.offset = (event.clientX - drag.originX) / S.pps;
    const shift = drag.offset * S.pps;
    if (drag.kind === "resize") {
      // Live feedback has to stay above zero width or the element collapses and
      // the grip disappears from under the cursor mid-drag.
      if (drag.side === "l") {
        const width = Math.max(6, drag.startWidth - shift);
        drag.element.style.left = drag.startLeft + (drag.startWidth - width) + "px";
        drag.element.style.width = width + "px";
      } else {
        drag.element.style.width = Math.max(6, drag.startWidth + shift) + "px";
      }
    } else {
      drag.element.style.left = drag.startLeft + shift + "px";
    }
    say(`${drag.kind} ${drag.id}: ${drag.offset >= 0 ? "+" : ""}${drag.offset.toFixed(2)}s`);
  });

  window.addEventListener("mouseup", async () => {
    if (!drag) return;
    const moved = drag;
    drag = null;
    moved.element.classList.remove("resizing");
    if (Math.abs(moved.offset) < 0.01) {
      // A click, not a drag. Put the element back where it was and leave the DOM
      // alone so a double-click still has something to land on.
      moved.element.style.left = moved.startLeft + "px";
      moved.element.style.width = moved.startWidth + "px";
      return;
    }
    if (moved.kind === "line") {
      await edit({op: "shift_line", line: moved.id, by: round(moved.offset)});
      return;
    }
    const word = lines().flatMap((l) => l.words).find((w) => w.id === moved.id);
    if (moved.kind === "resize") {
      const bound = moved.side === "l"
        ? {start: round(word.start + moved.offset)}
        : {end: round(word.end + moved.offset)};
      await edit({op: "resize_word", word: moved.id, ...bound});
    } else {
      await edit({op: "move_word", word: moved.id, to: round(word.start + moved.offset)});
    }
  });
}
