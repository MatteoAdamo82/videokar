// Wiring, keyboard, and the one poll that notices the server has gone away.
import {$, audio, say} from "./dom.js";
import {S} from "./store.js";
import {post, report} from "./api.js";
import {tick, seek, stepRate, wireTransport} from "./transport.js";
import {render, wireTimeline} from "./timeline.js";
import {closeSheet, wireSheet} from "./sheet.js";
import {openLibrary} from "./library.js";
import {openExport} from "./export.js";
import {load} from "./session.js";

async function undo() {
  try {
    const result = await post("/api/undo");
    S.doc = result;
    S.undoDepth = result.undo_depth;
    $("#undo").disabled = S.undoDepth === 0;
    render();
    say(`undone · ${S.doc.suspicious.length} flagged`, "good");
  } catch (err) { say(err.message, "bad"); }
}

function wireKeys() {
  window.addEventListener("keydown", (event) => {
    if (event.target.tagName === "INPUT") return;
    if (event.code === "Space") { event.preventDefault(); $("#play").click(); }
    if ((event.metaKey || event.ctrlKey) && event.key === "z") { event.preventDefault(); $("#undo").click(); }
    if (event.key === "ArrowLeft") seek(audio.currentTime - (event.shiftKey ? 5 : 1));
    if (event.key === "ArrowRight") seek(audio.currentTime + (event.shiftKey ? 5 : 1));
    if (event.key === "l") $("#loop").click();
    if (event.key === "Escape") closeSheet();
    // Step through the speeds without reaching for the menu.
    if (event.key === "[") stepRate(-1);
    if (event.key === "]") stepRate(+1);
  });
}

// One quiet poll: a server that dies while the page is open otherwise leaves it
// looking frozen until something is clicked.
function watchServer() {
  setInterval(async () => {
    try {
      await fetch("/api/library", {method: "HEAD"});
      document.body.classList.remove("offline");
    } catch {
      document.body.classList.add("offline");
      say("the server is not answering — is `videokar serve` still running?", "bad");
    }
  }, 5000);
}

wireTransport();
wireTimeline();
wireSheet();
wireKeys();
watchServer();
$("#undo").onclick = undo;
$("#library").onclick = openLibrary;
$("#export").onclick = openExport;

load().then(tick).catch(report);
