// The page's furniture: the handful of elements everything else reaches for,
// and the formatting that turns numbers into something readable.

export const $ = (s) => document.querySelector(s);

export const audio = $("#audio"), scroll = $("#scroll"), track = $("#track"),
  linesEl = $("#lines"), head = $("#playhead"), wave = $("#wave"), side = $("#side"),
  veil = $("#veil"), sheet = $("#sheet");

// m:ss.cc — the clock and the ruler both want hundredths.
export const fmt = (t) =>
  `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}.${
    String(Math.floor((t % 1) * 100)).padStart(2, "0")}`;

export const mmss = (s) => {
  // Round the total, not the seconds: 179.81 rounded per-part reads "2:60".
  const total = Math.round(s);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
};

export const say = (msg, kind = "") => {
  const s = $("#status");
  s.textContent = msg;
  s.className = kind;
};

export const escapeHtml = (s) =>
  s.replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

// Milliseconds are as fine as the document is written; sending a float's full
// tail would only make the JSON harder to read by hand.
export const round = (v) => Math.round(v * 1000) / 1000;
