// The Songs panel: what is in the folder, opening one, discarding one, and
// starting an alignment from an audio file and pasted lyrics.
import {$, sheet, say, escapeHtml as esc, mmss} from "./dom.js";
import {api, post, report} from "./api.js";
import {openSheet, closeSheet, sheetSay, watchJob} from "./sheet.js";
import {adopt} from "./session.js";

const songItem = (song, open) => `
  <div class="item ${song.path === open ? "current" : ""}" data-path="${esc(song.path)}">
    <span>${esc(song.title)}</span>
    <span class="meta">${song.lines} lines · ${song.flagged} flagged · ${mmss(song.duration)}</span>
    <button class="discard" data-path="${esc(song.path)}" data-title="${esc(song.title)}"
            title="move to .trash">✕</button>
  </div>`;

// Asked in the row rather than through window.confirm: a browser that has been
// told to stop showing dialogs answers those silently, and the button then
// appears to do nothing at all.
function askDiscard(button) {
  const row = button.closest(".item");
  if (row.querySelector(".confirm")) return;
  const ask = document.createElement("span");
  ask.className = "confirm";
  ask.innerHTML = `<b>move to .trash?</b>
    <button class="yes">move</button><button class="no">keep</button>`;
  row.append(ask);
  ask.querySelector(".no").onclick = (e) => { e.stopPropagation(); ask.remove(); };
  ask.querySelector(".yes").onclick = async (e) => {
    e.stopPropagation();
    try {
      await post("/api/discard", {path: button.dataset.path, media: false});
      sheetSay(`${button.dataset.title} moved to .trash — it can be brought back`, "good");
      $("#library").click();
    } catch (err) { sheetSay(err.message, "bad"); }
  };
}

async function startAlign() {
  const file = $("#newaudio").files[0];
  const lyrics = $("#newlyrics").value;
  if (!file) return sheetSay("pick an audio file first", "bad");
  if (!lyrics.trim()) return sheetSay("paste the lyrics — they are what gets aligned", "bad");
  const body = new FormData();
  body.append("audio", file);
  body.append("lyrics", lyrics);
  body.append("separate", $("#sep").checked ? "true" : "false");
  $("#startalign").disabled = true;
  $("#startalign").textContent = "Aligning…";
  sheetSay(`sending ${file.name}…`);
  try {
    const job = await api("/api/songs", {method: "POST", body});
    watchJob(job, async (finished) => {
      if (finished.status !== "done") return;
      adopt(await post("/api/open", {path: finished.document}));
      closeSheet();
    });
  } catch (err) {
    sheetSay(err.message, "bad");
    report(err);
  } finally {
    $("#startalign").disabled = false;
    $("#startalign").textContent = "Align";
  }
}

export async function openLibrary() {
  let data;
  try { data = await api("/api/library"); } catch (err) { return report(err); }
  openSheet(`
    <h1>Songs</h1>
    <p>${esc(data.workdir)}</p>
    <h2>open</h2>
    <div id="songlist">${
      data.songs.length
        ? data.songs.map((song) => songItem(song, data.open)).join("")
        : "<p>Nothing here yet. Add a song below.</p>"
    }</div>
    <h2>new song</h2>
    <label>audio file<input type="file" id="newaudio" accept="audio/*"></label>
    <label>lyrics — Suno tags and (second voice) lines are understood
      <textarea id="newlyrics" placeholder="[Verse 1]&#10;Seven o'clock, she's at the door&#10;(she's not mine, I know)"></textarea>
    </label>
    <div class="actions">
      <button class="primary" id="startalign">Align</button>
      <label style="margin:0;display:flex;gap:6px;align-items:center">
        <input type="checkbox" id="sep" checked style="width:auto"> isolate the vocal first
      </label>
    </div>
    <p class="sheetsay"></p>
    <div id="jobs"></div>`);

  for (const button of sheet.querySelectorAll("#songlist .discard")) {
    button.onclick = (event) => { event.stopPropagation(); askDiscard(button); };
  }
  for (const item of sheet.querySelectorAll("#songlist .item")) {
    item.onclick = async () => {
      try {
        adopt(await post("/api/open", {path: item.dataset.path}));
        closeSheet();
      } catch (err) { say(err.message, "bad"); }
    };
  }
  $("#startalign").onclick = startAlign;
}
