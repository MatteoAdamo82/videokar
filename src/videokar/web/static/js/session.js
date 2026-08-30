// Opening a document and taking it up: everything that has to be refreshed
// when the page starts on one, or is pointed at another.
import {$, audio, say} from "./dom.js";
import {S, lines} from "./store.js";
import {api} from "./api.js";
import {setRate} from "./transport.js";
import {layout, render} from "./timeline.js";

function summarise() {
  $("#title").textContent = S.doc.song.audio.path.split("/").pop();
  say(`${lines().length} lines · ${S.doc.suspicious.length} flagged`);
}

export async function load() {
  setRate(parseFloat($("#speed").value));
  try {
    S.doc = await api("/api/song");
  } catch {
    // Started on the library rather than on a document. That is a normal way
    // in, not an error to shout about.
    say("no song open yet — pick one, or add one");
    $("#library").click();
    return;
  }
  S.duration = S.doc.song.audio.duration;
  audio.src = "/api/audio";
  try { S.peaks = await api("/api/peaks"); } catch { S.peaks = null; }
  layout();
  render();
  summarise();
}

// A different song, from the library or from a finished alignment.
export function adopt(result) {
  S.doc = result;
  S.duration = result.song.audio.duration;
  // The query defeats the cache: the previous song is at the same URL.
  audio.src = "/api/audio?" + Date.now();
  S.selected = null;
  S.undoDepth = 0;
  $("#undo").disabled = true;
  S.peaks = null;
  api("/api/peaks").then((p) => { S.peaks = p; layout(); render(); }).catch(() => {});
  layout();
  render();
  summarise();
}
