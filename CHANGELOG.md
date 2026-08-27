# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Project scaffolding: `pyproject.toml` (Python 3.12, ML deps behind extras),
  MIT license, package layout under `src/videokar/`.
- Lyrics parser for Suno-style text: `[Section]` tags kept but never aligned,
  fully parenthesised lines marked as the second voice, and a guaranteed 1:1
  mapping between the tokens drawn on screen and the words handed to the
  aligner.
- Token normalisation for the aligner alphabet: typographic apostrophes folded,
  accents stripped, hyphens joined, and English digits spelled out so `7`
  matches a sung "seven".
- `videokar lyrics FILE` to inspect a parse before spending time on separation
  and alignment, with `--json` for machine use.
- The original chat prototype preserved under `docs/prototype/` as reference,
  and the ladycat track under `examples/ladycat/` as the real-world test case.
- Vocal separation with demucs (`htdemucs`), cached on disk under a hash of the
  audio contents so a rename or a move still hits the same entry.
- Energy-based voice activity detection over the isolated vocal stem, with an
  absolute noise floor so an instrumental is not reported as wall-to-wall
  singing.
- Forced alignment with `torchaudio`'s MMS_FA, using the star token between
  every pair of words so instrumental breaks and ad-libs have somewhere to go
  instead of stretching the next lyric across them. The acoustic model runs on
  the Apple GPU; the Viterbi pass falls back to the CPU, which is the only
  device `forced_align` implements.
- Overlapped, trimmed chunking of the acoustic model so a three-minute track
  does not need a quadratic attention matrix, and so chunk boundaries do not
  shift every timing after them.
- Per-line confidence scoring and suspicious-line flags — smeared, crammed,
  internal gap, outside the vocal, overlapping the next line — with the score
  check taken relative to the track's own median rather than an absolute
  threshold that sung audio would fail everywhere.
- `examples/ladycat/README.md` documenting what the reference track exercises.

- The pivot document: a JSON file holding timing and structure and nothing about
  appearance, with stable short ids, seconds as plain numbers, and one line per
  word so hand editing produces a readable diff. Words are authoritative over
  `line.text` and over `norm`, both of which are treated as derived and reported
  when they fall out of date.
- `videokar align AUDIO --lyrics FILE` and `videokar check SONG.json`.
- `check` recomputes line flags from the document rather than trusting what
  alignment wrote, so it stays honest after a hand edit, and reports what hand
  editing can break: a stale line text, a stale aligner form, a line marked sung
  with no timings, a word that ends before it starts, lines out of order.

- The renderer: text laid out once per line and cached, per-word colouring as
  the vocal passes, a second voice drawn in its own style, and a ball that hops
  from word to word on an arc so it lands on the beat rather than chasing it.
- `videokar render SONG.json` writing ProRes 4444 with alpha, H.264 mp4 with the
  audio muxed in, or a numbered PNG sequence.
- Fixed font size with an explicit floor: a line too wide to fit shrinks only as
  far as `min_scale` and wraps past that, rather than resizing itself line by
  line.
- Segmented encoding with a stream-copy concat, and a frame-size guard — raw
  video carries no framing, so a mismatched frame would have produced a torn
  video rather than an error.

- `videokar fix` — hand correction of timings, with the ripple stopping at
  pinned lines: `list`, `shift`, `stretch`, `word`, `pin` and `mute`, each with
  `--dry-run`. Edited words are marked `manual`, and any edit that would invert
  the timeline is refused with the conflict named rather than written.

- `videokar serve` — the sync view: waveform of the isolated vocal, draggable
  lines and words, double-click to retype a word the aligner misheard, pin and
  mute, playback with live highlighting, and undo. Every edit goes through the
  same operations as `videokar fix`, so the anchor rules and the guards against
  inverting the timeline are shared rather than reimplemented.
- Loop the selected line in the sync view, shown as a band over the waveform.
  Together with the speed control this is the loop you actually work in: run one
  line at half speed until the ball lands where it should.
- Playback speed in the sync view: 0.25× to 1×, from the header or with `[` and
  `]`, with pitch correction so slowed words stay intelligible.
- Word blocks in the sync view can be resized from either edge, so a held or a
  clipped syllable can be given the length it actually has. The bound checks now
  also look at the line on either side: a line's span comes from its words, so
  stretching the first or last one moves the line's edge.
- Waveform peaks computed from the vocal stem and cached beside it, one byte per
  bucket at a hundred buckets a second.
- `set_word_text` recomputes the aligner form and rebuilds the line text, so a
  correction made in the view leaves nothing for `check` to report as stale.

- Configuration: a typed style schema with bounds, choices and descriptions,
  four presets (`alpha`, `youtube`, `shorts`, `minimal`), and layered resolution
  — defaults, preset, file, command-line flags — merged per key rather than per
  section. Colours are hex, and `videokar config init` writes a file with every
  setting explained in place from the schema's own descriptions.
- `videokar config presets | init | show`, with `--schema` printing the JSON
  schema of every setting, so an editor can be generated from it rather than
  written by hand against it.

- The sync view became the way in: a library of the documents in a folder,
  aligning a new song from an uploaded audio file and pasted lyrics, and
  exporting the video — each of the slow ones running as a background job with
  progress, and the render offered as a download when it finishes.
- `videokar serve` now takes an optional document and a `--dir`, so it can start
  on the library rather than needing a document to exist first.

### Fixed

- Rendering at anything much smaller than 1080p was broken. Font size followed
  the frame height but margins, outline width and the ball's radius, arc and
  clearance were fixed pixel counts tuned at 1080p, so at 320x180 the margins
  left 96 pixels of usable width, the vertical margin pushed bottom-anchored
  text to the top, and the ball's arc placed it eighty pixels above the picture
  — no bounce visible at all. Every measurement now defaults to a fraction of
  the frame, with explicit values still winning, and a default 1080p render is
  unchanged.
- The resolved ball is now a distinct type from the configured one, so
  arithmetic on an unresolved dimension cannot compile past review.

- The download link in the sync view could save an error page as the video.
  It pointed at the job that produced the file, and jobs live in memory, so a
  server restart turned the link into a 404 whose JSON body `<a download>` then
  wrote to disk. Rendered files are now served by name from the working
  directory, which outlives the job, HEAD is answered rather than refused with
  a JSON 405, and the page checks the response before saving anything.
- Clicking a line in the sync view moved the clock but not the view, so while
  paused it looked as though nothing had happened. Seeking now brings the
  timeline with it.
- `load_song` raised `AttributeError` on JSON that parsed to something other
  than an object — which is what any unrelated JSON in the folder does. It now
  says the file is not a videokar document, which is what lets the library scan
  a folder safely.
- A duration of 179.81s displayed as "2:60": the parts were rounded separately.

- `check` kept flagging lines the user had already pinned. A low score is the
  acoustic model's opinion of its own confidence, and pinning is a person
  overruling it; on the reference track five of eight flags sat on lines already
  fixed by hand, hiding the three that still needed attention. Pinned lines keep
  their score but lose that flag. The structural flags stay, since those describe
  the shape of what is in the file rather than a guess about it.

- The ball twitched on quick words. It drew one arc per word, and sung words are
  often only tens of milliseconds apart — "I" to "know" is 20ms on the reference
  track, half a frame at 25fps, with 41% of all gaps under a third of a second.
  Words closer together than `min_bounce` now share one bounce, landing over the
  middle of the group; the shortest hop on the reference track goes from 20ms to
  360ms, and 200 words become 145 bounces.

- Lines vanished before their last word was sung. The exit time was clamped to
  `next.start - lead_in`, and lines in a real song follow each other about forty
  milliseconds apart, so on the reference track 24 of 36 lines were cut short —
  up to 0.78s early — and each early exit pulled the next line in early too,
  which made the whole video look out of step with the music. A line's window
  now always covers the line, and fades are fitted into the room left over
  rather than eating into the singing.

### Changed

- Text no longer changes size from line to line. Shrinking a too-wide line was
  on by default at `min_scale=0.7`, so long lines were quietly drawn smaller
  than short ones. The default is now 1.0 — never shrink, wrap instead — and
  shrinking is opt-in through `--min-scale`.
- The default font size is derived from the frame height rather than fixed at
  64px, which was too large at 720p and made six lines wrap. It is still one
  fixed size for the whole render.
- `videokar render` reports how many lines had to wrap.

- Square-bracket tags are now split two ways: a tag naming a song section
  (`[Chorus - wide, stacked harmonies]`, `[Fade-Outro]`) opens a section, while
  a performance direction (`[higher harmony]`, `[all voices]`) is carried on the
  lines that follow it. Previously every tag opened a section, which chopped a
  chorus into three.
- `videokar lyrics` prints sections as headers rather than as a column, so a
  long tag no longer wraps every line of the song, and shows empty sections and
  directions.
