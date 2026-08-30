// What the page knows, in one object rather than a drawer of loose variables:
// modules can read a live binding but not assign to one, and every one of these
// is written from more than one place.

export const S = {
  doc: null,        // the whole /api/song answer: song, suspicious, off_the_attack
  peaks: null,
  pps: 110,         // pixels per second — the zoom
  duration: 0,
  selected: null,   // line id
  follow: true,     // does the view chase the playhead
  undoDepth: 0,
  loopOn: false,
  // Word id -> word, rebuilt when the document changes rather than looked up by
  // scanning every word for every word on every frame.
  wordIndex: new Map(),
};

export const lines = () =>
  (S.doc ? S.doc.song.sections.flatMap((s) => s.lines) : []);

export const lineById = (id) => lines().find((l) => l.id === id);

// Enough run-up to hear the beat the first word lands on, and enough tail not to
// clip the last one before it comes round again.
export const LOOP_LEAD = 0.6, LOOP_TAIL = 0.4;

export function loopBounds() {
  if (!S.loopOn || !S.selected) return null;
  const line = lineById(S.selected);
  if (!line || line.start == null) return null;
  return [Math.max(0, line.start - LOOP_LEAD), line.end + LOOP_TAIL];
}

export const wordsText = (line) => line.words.map((w) => w.text).join(" ");
