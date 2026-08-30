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
  <label class="wide" data-when="sprite">…or add a PNG with transparency
    <input type="file" id="newsprite" accept="image/png">
  </label>`;

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
    file: fileTab(data, was),
  };
  return `
    <h1>Export</h1>
    <p>Rendered next to the document, then offered as a download.</p>
    <img id="preview" class="preview" alt="preview">
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

const settings = () => ({
  preset: $("#expreset").value,
  anchor: $("#expanchor").value,
  // A percentage of the frame, so the same choice holds at any resolution.
  margin_pct: Number($("#expmargin").value),
  paren_scale: Number($("#expparen").value) / 100,
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
  const kind = $("#expbounce").value;
  for (const label of document.querySelectorAll("[data-when]")) {
    label.hidden = !label.dataset.when.split(" ").includes(kind);
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
      refresh();
      // Kept either way — a solid badge is a legitimate thing to bounce — but
      // a lost alpha channel is worth hearing about before the render.
      const notes = result.warnings || [];
      say(notes.length ? `${result.name}: ${notes[0]}` : `${result.name} added`,
          notes.length ? "bad" : "good");
    } catch (err) { say(err.message, "bad"); }
  };
}

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

  openSheet(panel(data, fonts, was, marginPct));
  if (saved.saved) $("#savedto").textContent = `remembered in ${saved.path}`;
  wireTabs();

  const drawPreview = () => {
    const image = $("#preview");
    image.onerror = () =>
      say("the preview could not be drawn — check the status line above", "bad");
    image.src = "/api/frame?" + previewQuery(settings(), previewTime());
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
  };
  for (const id of ALL_CONTROLS) $("#" + id).oninput = refresh;
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
