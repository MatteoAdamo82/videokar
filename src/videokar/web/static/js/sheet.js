// The overlay panel the library and the export dialog are both drawn into, and
// the job it may be watching while it is open.
import {$, veil, sheet, say, escapeHtml} from "./dom.js";
import {api, report} from "./api.js";

let jobTimer = null;

export function openSheet(html) {
  sheet.innerHTML = html;
  veil.classList.add("open");
}

export function closeSheet() {
  veil.classList.remove("open");
  if (jobTimer) { clearInterval(jobTimer); jobTimer = null; }
}

export function sheetSay(message, kind = "") {
  const box = sheet.querySelector(".sheetsay");
  if (box) {
    box.textContent = message;
    box.className = "sheetsay " + kind;
  }
  say(message, kind);
}

// Poll a background job and draw it, until it stops running.
export function watchJob(job, onFinish) {
  const box = $("#jobs");
  if (!box) return;
  const draw = (state) => {
    const pct = state.progress >= 0 ? Math.round(state.progress * 100) : null;
    box.innerHTML = `
      <div class="job ${state.status}">
        <div><b>${escapeHtml(state.label)}</b> — ${escapeHtml(state.error || state.message || state.status)}</div>
        ${pct === null ? "" : `<div class="bar"><i style="width:${pct}%"></i></div>`}
        ${state.status === "done" && state.file
          ? `<p><a class="dl" href="#" data-file="${escapeHtml(state.file)}">download ${escapeHtml(state.file)}</a></p>`
          : ""}
      </div>`;
  };
  draw(job);
  if (jobTimer) clearInterval(jobTimer);
  jobTimer = setInterval(async () => {
    let state;
    try { state = await api(`/api/jobs/${job.id}`); } catch { return; }
    draw({...job, ...state});
    if (state.status !== "running") {
      clearInterval(jobTimer);
      jobTimer = null;
      const done = state.status === "done";
      sheetSay(done ? `${state.label} ready` : state.error, done ? "good" : "bad");
      if (onFinish) onFinish({...job, ...state});
    }
  }, 700);
}

async function saveOutput(name) {
  const url = "/api/output/" + encodeURIComponent(name);
  // Ask for one byte first. A plain <a download> saves whatever comes back,
  // so an error page ends up on disk as a file named like the video.
  try {
    const probe = await fetch(url, {headers: {Range: "bytes=0-0"}});
    if (!probe.ok && probe.status !== 206) {
      let detail = probe.statusText;
      try { detail = (await probe.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
  } catch (err) {
    report(err);
    return;
  }
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  say(`saving ${name}`, "good");
}

export function wireSheet() {
  veil.onclick = (event) => { if (event.target === veil) closeSheet(); };
  // Delegated from the sheet, which outlives the job panel inside it: attaching
  // per job meant a link stopped working as soon as anything redrew around it.
  sheet.onclick = async (event) => {
    const link = event.target.closest("a.dl");
    if (!link) return;
    event.preventDefault();
    await saveOutput(link.dataset.file);
  };
}
