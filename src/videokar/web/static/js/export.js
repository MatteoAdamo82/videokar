// The Export panel: the look of the video, a still to check it against, and the
// render itself. What is chosen here is written next to the document, so it
// survives a reload and the command line renders the same thing.
//
// The controls are grouped into tabs because there are now more than twenty of
// them, and a wall of that many is a wall whatever order they are in. The still
// sits above the tabs and stays put: every one of these settings is a question
// about how the frame looks, and switching tabs to lose sight of it would be
// the wrong way round.
import {$, audio, say, escapeHtml as esc} from "./dom.js";
import {lines} from "./store.js";
import {api, post, report} from "./api.js";
import {openSheet, sheetSay, watchJob} from "./sheet.js";
import {presetHeight, defaultSize, hexOf, overridesFrom, previewQuery} from "./style.js";

const FPS = [23.976, 24, 25, 29.97, 30, 50, 59.94, 60];
const ANCHORS = [["bottom", "near the bottom"], ["center", "in the middle"], ["top", "near the top"]];
const BOUNCERS = [["ball", "a circle"], ["sprite", "a PNG of your own"], ["none", "nothing"]];
const METERS = [["none", "nothing"], ["bars", "bars"], ["wave", "a wave"]];
const FITS = [["cover", "fill the frame, crop the rest"], ["contain", "fit it all in, pad the rest"],
              ["stretch", "stretch to fit exactly"]];

// Every control that redraws the still when it moves, by tab.
const TABS = [
  {
    id: "text",
    label: "Text",
    controls: ["expfont", "expsize", "expon", "expoff", "expout", "expoutcol",
               "expshadow", "expshadowcol", "expparen"],
  },
  {id: "place", label: "Position", controls: ["expanchor", "expmargin"]},
  {
    id: "bounce",
    label: "The ball",
    controls: ["expbounce", "expballcol", "expballsize", "expsprite", "expspritescale", "expsquash"],
  },
  {
    id: "music",
    label: "The music",
    controls: ["expmeter", "expbands", "expmetercol", "expmeterw", "expmeterh",
               "expmeterx", "expmetery", "expgap", "expmirror"],
  },
  {
    id: "behind",
    label: "Behind",
    controls: ["expbehind", "expfit", "expdim", "exploop"],
  },
  {id: "file", label: "The file", controls: ["expreset", "expfps", "expaudio"]},
];

const ALL_CONTROLS = TABS.flatMap((tab) => tab.controls);

function previewTime() {
  // The line under the playhead, or the next one along: previewing a frame with
  // nothing drawn on it tells you nothing about where the words sit.
  const here = audio.currentTime;
  const timed = lines().filter((line) => line.start != null);
  const active = timed.find((line) => line.start <= here && here <= line.end);
  if (active) return here;
  const next = timed.find((line) => line.start > here) || timed[0];
  return next ? next.start + Math.min(0.6, (next.end - next.start) / 2) : here;
}

const option = (value, label, chosen) =>
  `<option value="${value}" ${value === chosen ? "selected" : ""}>${label}</option>`;

const textTab = (fonts, was) => `
  <label>font<select id="expfont">
    <option value="">the system sans</option>
    ${fonts.map((f) => option(esc(f.path), esc(f.label), was.main.font)).join("")}
  </select></label>
  <label>size — <b id="expsizeout">1.0×</b> the default
    <input type="range" id="expsize" min="50" max="250"
           value="${Math.round((was.main.size ? was.main.size / defaultSize(was.preset) : 1) * 100)}">
  </label>
  <label>sung<input type="color" id="expon" value="${hexOf(was.main.colour_on, "#ffeebe")}"></label>
  <label>not yet sung<input type="color" id="expoff" value="${hexOf(was.main.colour_off, "#9695b4")}"></label>
  <label>outline — <b id="expoutout">3px</b>
    <input type="range" id="expout" min="0" max="12" value="${was.main.outline_width ?? 3}">
  </label>
  <label>outline colour<input type="color" id="expoutcol" value="${hexOf(was.main.outline, "#000000")}"></label>
  <label>shadow<select id="expshadow">
    <option value="" ${was.shadow.colour ? "" : "selected"}>none</option>
    <option value="on" ${was.shadow.colour ? "selected" : ""}>on</option>
  </select></label>
  <label>shadow colour<input type="color" id="expshadowcol" value="${hexOf(was.shadow.colour, "#000000")}"></label>
  <label>second voice — <b id="expparenout">0.72×</b> the main size
    <input type="range" id="expparen" min="50" max="120" value="${Math.round((was.paren.scale ?? 0.72) * 100)}">
  </label>
  <label class="wide">…or add a font file<input type="file" id="newfont" accept=".ttf,.otf,.ttc"></label>`;

const placeTab = (was, marginPct) => `
  <label>the words sit<select id="expanchor">
    ${ANCHORS.map(([v, t]) => option(v, t, was.layout.anchor || "bottom")).join("")}
  </select></label>
  <label>how far from that edge — <b id="expmarginout">11%</b> of the frame
    <input type="range" id="expmargin" min="0" max="70" value="${marginPct}">
  </label>`;

const bounceTab = (data, was) => `
  <label>what bounces<select id="expbounce">
    ${BOUNCERS.map(([v, t]) => option(v, t, was.ball.kind || "ball")).join("")}
  </select></label>
  <label data-when="ball">its colour
    <input type="color" id="expballcol" value="${hexOf(was.ball.colour, "#ff7846")}">
  </label>
  <label data-when="ball">its size — <b id="expballsizeout">1.0×</b>
    <input type="range" id="expballsize" min="30" max="400" value="${was.ball_scale}">
  </label>
  <label data-when="sprite">which PNG<select id="expsprite">
    <option value="">—</option>
    ${(data.sprites || []).map((n) => option(esc(n), esc(n), was.ball.sprite)).join("")}
  </select></label>
  <label data-when="sprite">its size — <b id="expspriteout">1.0×</b> the circle
    <input type="range" id="expspritescale" min="50" max="400" value="${Math.round((was.ball.sprite_scale ?? 1) * 100)}">
  </label>
  <label data-when="ball sprite">squash and stretch — <b id="expsquashout">off</b>
    <input type="range" id="expsquash" min="0" max="80" value="${Math.round((was.ball.squash ?? 0) * 100)}">
  </label>
  <label class="wide">…or add a PNG with transparency — adding one selects it
    <input type="file" id="newsprite" accept="image/png">
  </label>`;

const musicTab = (was) => `
  <label>draw the music<select id="expmeter">
    ${METERS.map(([v, t]) => option(v, t, was.meter.kind || "none")).join("")}
  </select></label>
  <label data-when="meter">its colour
    <input type="color" id="expmetercol" value="${hexOf(was.meter.colour, "#ffffff")}">
  </label>
  <label data-when="meter">how many bars — <b id="expbandsout">48</b>
    <input type="range" id="expbands" min="8" max="120" value="${was.meter.bands ?? 48}">
  </label>
  <label data-when="meter">space between them — <b id="expgapout">35%</b>
    <input type="range" id="expgap" min="0" max="80" value="${Math.round((was.meter.gap ?? 0.35) * 100)}">
  </label>
  <label data-when="meter">how wide — <b id="expmeterwout">72%</b> of the frame
    <input type="range" id="expmeterw" min="10" max="100" value="${Math.round((was.meter.width ?? 0.72) * 100)}">
  </label>
  <label data-when="meter">how tall — <b id="expmeterhout">13%</b>
    <input type="range" id="expmeterh" min="2" max="45" value="${Math.round((was.meter.height ?? 0.13) * 100)}">
  </label>
  <label data-when="meter">across — <b id="expmeterxout">50%</b>
    <input type="range" id="expmeterx" min="0" max="100" value="${Math.round((was.meter.x ?? 0.5) * 100)}">
  </label>
  <label data-when="meter">down — <b id="expmeteryout">50%</b>
    <input type="range" id="expmetery" min="0" max="100" value="${Math.round((was.meter.y ?? 0.5) * 100)}">
  </label>
  <label class="wide check" data-when="meter">
    <input type="checkbox" id="expmirror" ${was.meter.mirror === false ? "" : "checked"}>
    grow both ways from the middle — off stands the bars on a line
  </label>
  <p class="wide note">Read from the song itself, so it needs the audio the document names.</p>`;

const behindTab = (data, was) => `
  <label class="wide">what is behind the words<select id="expbehind">
    <option value="">nothing — the preset's own colour</option>
    ${(data.backgrounds || []).map((b) =>
      option(esc(b.name), `${esc(b.name)} — ${b.kind === "video" ? "a clip" : "a picture"}`,
             was.background.name)).join("")}
  </select></label>
  <label data-when="behind">how it fits<select id="expfit">
    ${FITS.map(([v, t]) => option(v, t, was.background.fit || "cover")).join("")}
  </select></label>
  <label data-when="behind">darken it — <b id="expdimout">off</b>
    <input type="range" id="expdim" min="0" max="80" value="${Math.round((was.background.dim ?? 0) * 100)}">
  </label>
  <label class="wide check" data-when="behind">
    <input type="checkbox" id="exploop" ${was.background.loop === false ? "" : "checked"}>
    repeat a clip shorter than the song — off holds its last frame instead
  </label>
  <label class="wide">…or add a picture or a clip
    <input type="file" id="newbehind" accept="image/*,video/*">
  </label>
  <p class="wide note">A background and a transparent overlay contradict each other: with one
     of these the file cannot be the alpha preset. Pick youtube or shorts under
     <b>The file</b>.</p>`;

const fileTab = (data, was) => `
  <label>preset<select id="expreset">
    ${data.presets.map((p) =>
      option(p, p === "alpha" ? "alpha — transparent ProRes 4444" : p, was.preset)).join("")}
  </select></label>
  <label>frame rate — match your editing timeline<select id="expfps">
    <option value="">from the preset</option>
    ${FPS.map((f) => `<option value="${f}" ${was.output.fps === f ? "selected" : ""}>${f}</option>`).join("")}
  </select></label>
  <label class="wide check">
    <input type="checkbox" id="expaudio" ${was.output.audio === false ? "" : "checked"}>
    carry the song in the file — it lines itself up in an editor, and cannot drift from it
  </label>
  <p class="wide note">A clip at a rate your project does not use gets conformed, which reads as
     the overlay falling further behind as the song goes on.</p>`;

function panel(data, fonts, was, marginPct) {
  const bodies = {
    text: textTab(fonts, was),
    place: placeTab(was, marginPct),
    bounce: bounceTab(data, was),
    music: musicTab(was),
    behind: behindTab(data, was),
    file: fileTab(data, was),
  };
  return `
    <h1>Export</h1>
    <p>Rendered next to the document, then offered as a download.</p>
    <div id="stage" class="stage"><img id="preview" class="preview" alt="preview"></div>
    <p class="hint">Drag the words or the meter to place them.</p>
    <div class="tabs" role="tablist">
      ${TABS.map((tab, i) =>
        `<button role="tab" data-tab="${tab.id}" class="${i ? "" : "on"}">${tab.label}</button>`).join("")}
    </div>
    ${TABS.map((tab, i) =>
      `<div class="grid tabbody" data-tab="${tab.id}" ${i ? 'hidden=""' : ""}>${bodies[tab.id]}</div>`).join("")}
    <div class="actions">
      <button class="primary" id="startrender">Render</button>
      <span id="savedto" class="meta"></span>
    </div>
    <p class="sheetsay"></p>
    <div id="jobs"></div>`;
}

// Where a drag has put things. Null means nobody has dragged it and the
// anchor, or the section's own default, still decides.
const placed = {text_x: null, text_y: null, meter_x: null, meter_y: null};

const settings = () => ({
  preset: $("#expreset").value,
  anchor: $("#expanchor").value,
  // A percentage of the frame, so the same choice holds at any resolution.
  margin_pct: Number($("#expmargin").value),
  paren_scale: Number($("#expparen").value) / 100,
  text_x: placed.text_x ?? 0.5,
  text_y: placed.text_y,
  bounce: $("#expbounce").value,
  sprite: $("#expsprite").value,
  sprite_scale: Number($("#expspritescale").value) / 100,
  ball_colour: $("#expballcol").value,
  ball_scale: Number($("#expballsize").value) / 100,
  squash: Number($("#expsquash").value) / 100,
  font: $("#expfont").value,
  size_scale: Number($("#expsize").value) / 100,
  colour_on: $("#expon").value,
  colour_off: $("#expoff").value,
  outline_width: Number($("#expout").value),
  outline: $("#expoutcol").value,
  shadow: $("#expshadow").value ? $("#expshadowcol").value : null,
  meter: $("#expmeter").value,
  bands: Number($("#expbands").value),
  meter_colour: $("#expmetercol").value,
  meter_w: Number($("#expmeterw").value) / 100,
  meter_h: Number($("#expmeterh").value) / 100,
  meter_x: placed.meter_x ?? Number($("#expmeterx").value) / 100,
  meter_y: placed.meter_y ?? Number($("#expmetery").value) / 100,
  gap: Number($("#expgap").value) / 100,
  mirror: $("#expmirror").checked,
  behind: $("#expbehind").value,
  fit: $("#expfit").value,
  dim: Number($("#expdim").value) / 100,
  loop: $("#exploop").checked,
});

function wireTabs() {
  for (const button of document.querySelectorAll(".tabs [data-tab]")) {
    button.onclick = () => {
      for (const other of document.querySelectorAll(".tabs [data-tab]")) {
        other.classList.toggle("on", other === button);
      }
      for (const body of document.querySelectorAll(".tabbody")) {
        body.hidden = body.dataset.tab !== button.dataset.tab;
      }
    };
  }
}

// A PNG's size means nothing while a circle is bouncing, and the other way
// round. Hiding what does not apply is what makes the tab readable.
function showWhatApplies() {
  // Two independent modes, so a label says which words it wants to see.
  const on = [$("#expbounce").value];
  if ($("#expbehind").value) on.push("behind");
  if ($("#expmeter").value !== "none") on.push("meter");
  for (const label of document.querySelectorAll("[data-when]")) {
    label.hidden = !label.dataset.when.split(" ").some((word) => on.includes(word));
  }
}

function wireUploads(data, refresh) {
  $("#newfont").onchange = async () => {
    const file = $("#newfont").files[0];
    if (!file) return;
    const body = new FormData();
    body.append("font", file);
    try {
      const result = await api("/api/fonts", {method: "POST", body});
      const picker = $("#expfont");
      picker.innerHTML = `<option value="">the system sans</option>` +
        result.fonts.map((f) => `<option value="${esc(f.path)}">${esc(f.label)}</option>`).join("");
      picker.value = result.font.path;
      refresh();
      say(`${result.font.label} added`, "good");
    } catch (err) { report(err); }
  };

  $("#newbehind").onchange = async () => {
    const file = $("#newbehind").files[0];
    if (!file) return;
    const body = new FormData();
    body.append("media", file);
    try {
      const result = await api("/api/backgrounds", {method: "POST", body});
      const picker = $("#expbehind");
      picker.innerHTML = `<option value="">nothing — the preset's own colour</option>` +
        result.backgrounds.map((b) =>
          `<option value="${esc(b.name)}">${esc(b.name)} — ${
            b.kind === "video" ? "a clip" : "a picture"}</option>`).join("");
      picker.value = result.name;
      data.backgrounds = result.backgrounds;
      refresh();
      say(`${result.name} is behind the words now`, "good");
    } catch (err) { say(err.message, "bad"); }
  };

  $("#newsprite").onchange = async () => {
    const file = $("#newsprite").files[0];
    if (!file) return;
    const body = new FormData();
    body.append("image", file);
    try {
      const result = await api("/api/sprites", {method: "POST", body});
      const picker = $("#expsprite");
      picker.innerHTML = `<option value="">—</option>` +
        result.sprites.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
      picker.value = result.name;
      data.sprites = result.sprites;
      // Adding one is how you say you want it. Leaving the circle selected
      // would put the file in the folder and change nothing on screen, which
      // reads as the upload having failed.
      $("#expbounce").value = "sprite";
      refresh();
      // Kept either way — a solid badge is a legitimate thing to bounce — but
      // a lost alpha channel is worth hearing about before the render.
      const notes = result.warnings || [];
      say(notes.length ? `${result.name}: ${notes[0]}` : `${result.name} added`,
          notes.length ? "bad" : "good");
    } catch (err) { say(err.message, "bad"); }
  };
}

const HANDLES = {
  words: "the words",
  meter: "the meter",
};

// One handle per thing the frame reports, laid over the preview at the same
// fractions. Rebuilt on every redraw, because what is on screen has moved.
function layHandles(boxes) {
  const stage = $("#stage");
  stage.querySelectorAll(".handle").forEach((old) => old.remove());
  for (const [name, label] of Object.entries(HANDLES)) {
    const box = boxes[name];
    if (!box) continue;
    const handle = document.createElement("div");
    handle.className = "handle";
    handle.dataset.what = name;
    handle.title = `drag ${label}`;
    const [x, y, w, h] = box;
    Object.assign(handle.style, {
      left: `${x * 100}%`,
      top: `${y * 100}%`,
      width: `${w * 100}%`,
      height: `${h * 100}%`,
    });
    stage.append(handle);
  }
}

function wireDragging(refresh) {
  const stage = $("#stage");
  let drag = null;

  stage.addEventListener("mousedown", (event) => {
    const handle = event.target.closest(".handle");
    if (!handle) return;
    event.preventDefault();
    const frame = $("#preview").getBoundingClientRect();
    const box = handle.getBoundingClientRect();
    drag = {
      what: handle.dataset.what,
      frame,
      // Grab it where it was taken hold of, so it does not jump to the cursor.
      offsetX: (box.left + box.width / 2 - event.clientX) / frame.width,
      offsetY: (box.top + box.height / 2 - event.clientY) / frame.height,
      handle,
    };
    handle.classList.add("dragging");
  });

  window.addEventListener("mousemove", (event) => {
    if (!drag) return;
    const x = clamp((event.clientX - drag.frame.left) / drag.frame.width + drag.offsetX);
    const y = clamp((event.clientY - drag.frame.top) / drag.frame.height + drag.offsetY);
    if (drag.what === "words") {
      placed.text_x = round3(x);
      placed.text_y = round3(y);
    } else {
      placed.meter_x = round3(x);
      placed.meter_y = round3(y);
      $("#expmeterx").value = Math.round(x * 100);
      $("#expmetery").value = Math.round(y * 100);
    }
    // Move the handle now and let the frame catch up: the redraw is debounced,
    // and a handle that lags the cursor feels broken.
    drag.handle.style.left = `${(x - drag.handle.offsetWidth / drag.frame.width / 2) * 100}%`;
    drag.handle.style.top = `${(y - drag.handle.offsetHeight / drag.frame.height / 2) * 100}%`;
    refresh();
  });

  window.addEventListener("mouseup", () => {
    if (!drag) return;
    drag.handle.classList.remove("dragging");
    drag = null;
    refresh();
  });
}

const clamp = (v) => Math.min(1, Math.max(0, v));
const round3 = (v) => Math.round(v * 1000) / 1000;

export async function openExport() {
  let data, saved, fonts;
  try {
    data = await api("/api/library");
    fonts = (await api("/api/fonts")).fonts;
    // Restored from the folder rather than from this tab, so it survives a
    // reload, another browser, and the CLI reading the same file.
    saved = await api("/api/style");
  } catch (err) { return report(err); }

  const was = {
    preset: saved.preset || "alpha",
    layout: saved.overrides.layout || {},
    ball: saved.overrides.ball || {},
    paren: saved.overrides.paren || {},
    output: saved.overrides.output || {},
    main: saved.overrides.main || {},
    shadow: saved.overrides.shadow || {},
    background: saved.overrides.background || {},
    meter: saved.overrides.meter || {},
  };
  const marginPct = was.layout.margin_y != null
    ? Math.round(was.layout.margin_y * 100 / presetHeight(was.preset))
    : 11;
  // The saved radius is in pixels; the control is a multiple of what the ball
  // would have been, so it has to be read back the same way round.
  const savedSize = was.main.size || defaultSize(was.preset);
  was.ball_scale = was.ball.radius
    ? Math.round((was.ball.radius / (savedSize * 0.25)) * 100)
    : 100;

  placed.text_x = was.layout.x ?? null;
  placed.text_y = was.layout.y ?? null;
  placed.meter_x = null;
  placed.meter_y = null;
  openSheet(panel(data, fonts, was, marginPct));
  if (saved.saved) $("#savedto").textContent = `remembered in ${saved.path}`;
  wireTabs();

  // Fetched rather than set as a src: the answer carries the boxes each thing
  // ended up in, which is what the handles are laid over — and when it is a
  // refusal instead, the reason is in the body rather than nowhere.
  let showing = null;
  const drawPreview = async () => {
    const url = "/api/frame?" + previewQuery(settings(), previewTime());
    let answer;
    try {
      answer = await fetch(url);
    } catch {
      return say("the preview could not be drawn", "bad");
    }
    if (!answer.ok) {
      let detail = "the preview could not be drawn";
      try { detail = (await answer.json()).detail || detail; } catch {}
      return say(detail, "bad");
    }
    const blob = await answer.blob();
    if (showing) URL.revokeObjectURL(showing);
    showing = URL.createObjectURL(blob);
    $("#preview").src = showing;
    let boxes = {};
    try { boxes = JSON.parse(answer.headers.get("X-Videokar-Boxes") || "{}"); } catch {}
    layHandles(boxes);
  };

  let previewTimer = null;
  const refresh = () => {
    // Dragging a slider fires an event per pixel; without this the page asks
    // for forty frames on the way to the one you wanted.
    clearTimeout(previewTimer);
    previewTimer = setTimeout(drawPreview, 120);
    showWhatApplies();
    const s = settings();
    $("#expmarginout").textContent = `${s.margin_pct}%`;
    $("#expparenout").textContent = `${s.paren_scale.toFixed(2)}×`;
    $("#expspriteout").textContent = `${s.sprite_scale.toFixed(1)}×`;
    $("#expballsizeout").textContent = `${s.ball_scale.toFixed(1)}×`;
    $("#expsquashout").textContent = s.squash ? s.squash.toFixed(2) : "off";
    $("#expsizeout").textContent = `${s.size_scale.toFixed(2)}×`;
    $("#expoutout").textContent = s.outline_width ? `${s.outline_width}px` : "none";
    $("#expbandsout").textContent = String(s.bands);
    $("#expgapout").textContent = `${Math.round(s.gap * 100)}%`;
    $("#expmeterwout").textContent = `${Math.round(s.meter_w * 100)}%`;
    $("#expmeterhout").textContent = `${Math.round(s.meter_h * 100)}%`;
    $("#expmeterxout").textContent = `${Math.round(s.meter_x * 100)}%`;
    $("#expmeteryout").textContent = `${Math.round(s.meter_y * 100)}%`;
  };
  for (const id of ALL_CONTROLS) $("#" + id).oninput = refresh;
  // A slider moved by hand is a decision: it takes the position back from
  // wherever a drag had put it.
  $("#expmeterx").addEventListener("input", () => { placed.meter_x = null; });
  $("#expmetery").addEventListener("input", () => { placed.meter_y = null; });
  $("#expanchor").addEventListener("input", () => { placed.text_y = null; });
  $("#expmargin").addEventListener("input", () => { placed.text_y = null; });
  wireDragging(refresh);
  refresh();

  wireUploads(data, refresh);

  $("#startrender").onclick = async () => {
    $("#startrender").disabled = true;
    const s = settings();
    const fps = $("#expfps").value;
    const overrides = overridesFrom(s, fps, $("#expaudio").checked);
    try {
      // Saved before rendering, so the settings survive whatever the render
      // does — and so the same result can be had from the command line.
      await post("/api/style", {preset: s.preset, overrides});
      $("#savedto").textContent = "remembered";
      watchJob(await post("/api/render", {
        preset: s.preset,
        fps: fps ? Number(fps) : null,
        overrides,
      }));
    } catch (err) {
      sheetSay(err.message, "bad");
      report(err);
    } finally {
      $("#startrender").disabled = false;
    }
  };
}
