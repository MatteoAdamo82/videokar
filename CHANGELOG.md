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

- The export dialog gained the settings worth choosing before a render —
  where the words sit, how far from that edge, and the second voice's size —
  above a live preview frame of the line under the playhead. Rendering blind and
  waiting minutes to see the result is not a way to choose a position.
- `GET /api/frame` renders a single small frame with a given style, and
  `POST /api/render` accepts any settings the style schema knows rather than a
  fixed handful, so the page can offer a control without the server learning its
  name.

- `videokar sprite FILE` inspects a candidate image before it is used: canvas,
  visible size, whether it has transparency, and the pixels it will be drawn at
  for a given output. Uploading one through the sync view reports the same
  warnings.
- The bouncing thing can be a PNG with transparency, from `--sprite`, the config
  file, or the export dialog in the sync view, which lists the PNGs in the
  working folder and accepts new ones. Sized on the visible pixels rather than
  the file's canvas, and centred on the point the circle would have occupied, so
  swapping one for the other does not move the bounce.

- `[ball] squash` stretches the ball along its direction of travel and squashes
  it across, area preserved. Off by default, and offered in the export dialog.

- The main text's font and size are in the export dialog. Fonts are scanned from
  the usual places on this machine and from the working folder, listed by family
  and style, with a file upload for one that is not installed. Size is offered
  as a multiple of what the preset already looks right at rather than as a pixel
  count, so it survives a change of resolution.
- The export dialog remembers. Rendering writes the choices to `videokar.toml`
  in the working folder and the dialog restores them next time — kept beside the
  song rather than in the browser, so a reload, a different machine or a hand
  edit all keep working, and the same file is what `videokar render -c` reads.
- The distance-from-the-edge control goes to 70% of the frame rather than 30%.

- `check` now measures each line's start against the nearest vocal attack, found
  in the stem, and flags the lines whose distance is an outlier for that song —
  reporting the distance and its sign, so it says which way to drag the line
  rather than only that something is odd. This is the failure the other checks
  cannot see: a line half a second late has an ordinary shape, an ordinary
  score, and sits inside a vocal region. On the reference track it surfaced four
  lines everything else called clean. Documents written before this can be
  checked without being aligned again — the attacks are computed from the audio
  and cached.


- A whole line can be retyped, from `videokar fix text` or by double-clicking
  the line in the view. Words that survive the change keep their timing — old
  and new wordings are matched up rather than the line being redistributed — so
  fixing a typo costs nothing and an added word is fitted between its
  neighbours.
- A song can be taken out of the folder from the view. It moves to a `.trash`
  subfolder rather than being deleted, and the audio it names is left alone.

- Two more overlay formats, both lossless and both carrying alpha: `animation`
  (QuickTime RLE) and `png_mov`. Measured on a four-minute 1080p overlay with a
  overlay, ProRes came to 0.94 GB against 0.15 GB and 0.26 GB, decoding within
  15% of each other. ProRes stays the default, being what an editor is
  tuned for.

- A drop shadow behind the words, off unless given a colour, with its offset and
  softness scaled to the text like everything else. Drawn once per line rather
  than once per frame, since its shape does not change while the line is up —
  a millisecond a frame instead of a blur every time.
- Text colours, outline and shadow are in the export dialog, with the live
  preview. `/api/frame` takes the same overrides a render does, so a control can
  be added to the page without the endpoint growing another parameter.

### Removed

- The music visualiser. It never looked good enough to keep — the spectrum, the
  waveform and the level meter each needed their own coaxing and none of them
  earned their place over the words. ffmpeg draws them well enough on its own
  for anyone who wants one, composited in an editor, which is where it started.

### Fixed




- The ✕ beside a song did nothing, and so did double-clicking a line to retype
  it. Both went through `window.confirm` and `window.prompt`, and a browser that
  has been told to stop showing dialogs — one checkbox, and the prompt for
  retyping a line is an easy way to end up ticking it — answers those silently
  and immediately. Both now ask on the page: the row turns into a "move to
  .trash? move / keep" question, and retyping a line opens a field over it.

- Clicking Align with nothing chosen looked like it did nothing. It said so, in
  the status bar in the far corner of a window covered by the dialog being
  looked at. Anything a dialog has to say now appears inside it, under the
  button that was pressed, and the button says while it is working.
- The accepted audio extensions were a short list that left out `.opus`, `.aac`
  and others ffmpeg reads perfectly well. It is a guard against an obvious
  mistake, not a codec list; ffprobe decides, and says so clearly when it
  cannot.

- Every export overwrote the same filename, so a copy downloaded earlier could
  not be told from the one just made — and since timings get corrected between
  exports, an old file looks exactly like a new one drifting. Exports are
  numbered now, and the name is reserved when the job starts rather than when
  the file appears, so two asked for in quick succession cannot collide.

- A margin larger than the frame pushed the words out of the picture and
  rendered a video with nothing on it. The block is held inside the frame.

- The sync view sent no cache headers at all, so a browser was free to cache it
  heuristically and keep running an older page against an updated server — which
  looks like the app freezing rather than like a stale cache. Everything live is
  now `no-store`; finished renders and audio stay cacheable. The page also stamps
  the version it is running into the header, so the question has an answer.
- The per-frame loop rebuilt the whole word list once per word — forty thousand
  comparisons and two hundred array allocations every frame. It builds an index
  when the document changes instead: 1.8ms per frame down to 0.05ms.

- The ball wobbled as it moved. Pillow's ellipse has no anti-aliasing and rounds
  its coordinates to whole pixels: the disc measured exactly 33x33 in every
  frame with only two distinct colours around its edge, while the position it
  was asked for moved in fractions, so the sliding stair-steps read as the shape
  breathing. It is supersampled now — around a hundred edge tones — and lands
  within a tenth of a pixel of where the geometry puts it, rather than six
  tenths.

- The sync view looked frozen when the server had stopped: a failed preview left
  the previous image on screen and a failed render said nothing that stood out.
  A request that never gets an answer is now told apart from one that comes back
  refused, since the two need different things from the reader, and a stopped
  server puts a band across the header and a message naming the command to
  restart. The page also polls quietly, so it notices without being clicked.
- The preview asked for a frame on every event a slider fired — forty-odd on the
  way to one value. It is debounced: twenty-one drag events now make one
  request.

- `kind = "sprite"` was in the schema from the start and drew nothing at all.

- Fractional frame rates were impossible: `fps` was an integer, so 23.976 and
  29.97 — the rates most editing timelines actually use — were refused outright.
  A clip at a rate the project does not use gets conformed, which reads as the
  overlay starting almost right and falling further behind as the song goes on.
  Rates are now fractions, and the NTSC ones are kept exact as 24000/1001 rather
  than the decimal, which would leave a smaller version of the same drift.

### Changed

- The transparent overlay preset now carries the song. A clip holding its own
  audio lines itself up in an editor and cannot drift away from it; `--no-audio`
  and a checkbox in the export dialog turn it off.

- The second voice is configured as a set of overrides rather than a whole
  second text style. Setting one thing on it — a matching size, say — used to
  reset everything else to the main voice's values, so the two voices became
  indistinguishable. `[paren]` now holds only what differs, and gains a `scale`
  so "same size as the main voice" is one line. An empty `[paren]` block now
  means "follow the main voice", which is also what it looks like it means.

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

### Added

- Continuous integration on Linux and macOS: ruff, the test suite with ffmpeg
  installed so the encoder is actually exercised, and a wheel build. It fails
  if anything in the non-integration set *skips* — a test that has quietly
  stopped running is worse than one that fails.
- The export dialog is grouped into four tabs — Text, Position, The ball, The
  file — with the preview above them, staying put. Inside a tab, a control that
  does not apply is hidden rather than greyed.
- The bouncing circle has a colour and a size in the dialog. Size is a multiple
  of what it would have been — a quarter of the text height — so the choice
  holds when the text size or the preset changes. "Nothing bounces" is offered
  as a third choice; the renderer already understood it.

### Changed

- `cli.py` is now a package with one module per command, and the helpers every
  command needs (`fail`, `open_song`, `resolve_audio`) live in `cli/common.py`
  instead of being private and scattered. The interface is unchanged: the help
  of all eighteen commands and subcommands is identical, line for line.
- The web routes moved out of `create_app` into `web/routes/`, five modules by
  area, with the session reaching a handler as a dependency rather than through
  a closure. `web/app.py` is now the assembly only. Every endpoint and every
  refusal answers exactly as before.
- The sync view's page carries no code of its own: the stylesheet and eleven
  ES modules are served alongside it. Two tests hold that line.
- The chunked upload loop, written out once per kind of file, is now
  `web/uploads.save_upload`. Form parameters use FastAPI's `Annotated` form, so
  the `B008` exemption that existed only for that file is gone.

### Fixed

- The `[ball]` section is now written in full, always saying which kind is
  meant, rather than leaving it to be inferred from whether a sprite is named.
  (This was committed as the fix for "a PNG cannot be taken back off", with a
  merge-per-key explanation that turns out to be wrong: `videokar.toml` is
  rewritten whole rather than merged, so the old code did drop the sprite. The
  change is still worth having — it is what let the circle have a colour and a
  size of its own — but it was not the bug that was reported.)
- In the preview, `squash` arrived as its own parameter and assigned over the
  whole `[ball]` section, dropping a colour and a radius sent alongside it.
- `.sheet label { display: block }` outranked the browser's own rule for
  `[hidden]`, so a hidden control in the dialog was still laid out and still on
  screen — it had merely stopped answering to the word.
- The PNG upload was gated on a PNG already being chosen, so with the circle
  selected there was no way to add one: hiding what does not apply had hidden
  the way out of the mode. It is always in the tab now, and adding a PNG
  selects it — putting a file in the folder and changing nothing on screen
  reads as the upload having failed.

### Added

- A background behind the words: a still, fitted and darkened once so every
  frame starts from it, or a clip, composited by ffmpeg while encoding.
  `videokar render --behind FILE --dim 0.4`, or a `[background]` section with
  `image`/`video`, `loop`, `fit` and `dim`. A short clip repeats, and carries on
  across a segment boundary rather than restarting at it. A background on a
  transparent export is a contradiction and is refused before the render.

- The background reaches the view: an upload that takes a picture or a clip, a
  **Behind** tab that lists what the folder holds and says which is which, and a
  preview that shows it — for a clip, the frame it would be showing at that
  point, extracted with ffmpeg, rather than a still that quietly lies.

### Fixed

- The web render never told the encoder about the background, so a clip was
  flattened away and the video came out on the preset's flat colour. An edit
  that was meant to pass it through had not matched the file it was aimed at,
  and nothing checked. There is a test now.
- The export dialog saved `background.name` into `videokar.toml` — a key the
  schema has never heard of, dropped in silence, so the same settings rendered
  from a terminal had no background at all. The name is resolved to a path on
  the way in, as it already was on the way to a render.
- A refused preview said only that it could not be drawn. It now reads the
  reason the server gave, which for a background on the alpha preset is a
  sentence naming the presets that do take one.
