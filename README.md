# videokar

[![ci](https://github.com/matteoadamo/videokar/actions/workflows/ci.yml/badge.svg)](https://github.com/matteoadamo/videokar/actions/workflows/ci.yml)

Bouncing-ball karaoke lyric videos from an audio track and its lyrics.

Built for lyric videos of AI-generated songs (Suno and friends): feed it the
mixdown and the lyrics you already have, get back a transparent overlay you can
drop on top of an animated clip in Final Cut — or a finished mp4 if you just
want the words on a background.

**Status: alpha.** The pipeline is being built one stage at a time. See
[CHANGELOG.md](CHANGELOG.md) for what already works.

## Why forced alignment, not transcription

Transcription models skip repetitions — ask Whisper for a chorus sung four times
and you get it once. So your lyrics file is the source of truth: videokar
*aligns* the words you supply against the vocal track rather than guessing what
was sung. Transcription is only the fallback for when you have no lyrics at all.

## Install

Requires Python 3.12 and `ffmpeg` on the PATH.

```bash
brew install ffmpeg
pipx install "videokar[all]"
```

The heavy ML wheels (torch, torchaudio, demucs, faster-whisper) live in extras.
`pipx install videokar` gives you lyrics parsing and rendering only; `[all]`
adds separation, alignment and transcription.

From a checkout:

```bash
uv venv --python 3.12 && uv pip install -e . --group dev
```

## Pipeline

```
audio + lyrics.txt
   ↓  demucs (htdemucs)          isolate the vocal, cached on disk
   ↓  VAD on the vocal track     vocal regions, so instrumentals stay empty
   ↓  forced alignment (MMS_FA)  per-word start/end
   → song.json                   the pivot format: readable, hand-editable
   ↓  renderer + ffmpeg
   → mp4 · ProRes 4444 with alpha · PNG sequence
```

`song.json` holds timing and structure only. Everything visual lives in a TOML
config, so restyling never costs you another alignment run.

## Lyrics format

Plain UTF-8 text. Two optional conventions, both Suno-native:

```
[Verse 1]
Seven o'clock, she's at the door
(she's not mine, I know)
```

* `[Section tags]` are kept in the output and grouped over their lines, but are
  never fed to the aligner. A tag may carry a description —
  `[Chorus - wide, stacked harmonies]` — and a section with no lines under it,
  like `[Instrumental]`, is kept as part of the song's shape.
* `[higher harmony]`, `[all voices]` and other performance directions appear
  *inside* a section. They are told apart from section tags by whether the tag
  names a song section, and are carried on the lines that follow rather than
  starting a new section.
* A line wrapped entirely in round brackets is the **second voice**. It follows
  the main one at 0.72× and dimmer, which is why some lines come out smaller
  than others — that is the answering vocal, not an accident. A line with
  brackets only in part of it (`(one) and (two)`) stays a normal line.

  ```toml
  [paren]
  scale = 1.0          # same size as the main voice; colours still differ
  colour_on = "#9be7c4"
  ```

  `[paren]` holds only what differs. Anything you leave out keeps following the
  main voice, so changing the size does not quietly take the colours with it.

Punctuation, capitals and accents are preserved for drawing and stripped for
alignment. Digits are spelled out in English, so `7` matches a sung "seven".

## Commands

| command | what it does |
| --- | --- |
| `videokar lyrics FILE` | parse a lyrics file and show how it will reach the aligner |
| `videokar align AUDIO --lyrics FILE` | separate, align, and write the pivot JSON |
| `videokar check SONG.json` | list the lines worth a second look |
| `videokar render SONG.json` | draw the overlay and encode it |
| `videokar fix SONG.json ...` | correct timings by hand |
| `videokar serve SONG.json` | the sync view, in a browser |
| `videokar config init` | write a configuration file, explained in place |

More commands land with their pipeline stage: `preview`, `build`, `transcribe`,
`cache`.

## The sync view

```bash
videokar serve                 # start on the library, in the current folder
videokar serve song.json       # or straight into one document
videokar serve --dir ~/songs   # any folder of documents
```

The view is a way in, not just a viewer for something the command line made.
**Songs** lists the documents in the folder, opens any of them, and takes an
audio file plus its lyrics to align a new one — the work runs in the background
with progress, and the document opens when it lands. **Export** renders the
video, transparent ProRes 4444 by default, and offers it as a download when it
is done — with **a live preview frame** above the controls, because choosing
where the words sit and then waiting three minutes to see it is not a way anyone
can work.

The controls are grouped into four tabs — **Text**, **Position**, **The ball**,
**The file** — with the preview above them, staying put: every one of these
settings is a question about how that frame looks, so losing sight of it to
change one would be the wrong way round. Inside a tab, what does not apply is
hidden rather than greyed: a PNG's size means nothing while a circle is
bouncing.

Position, distance from the edge and the second voice's size are under
**Position** and **Text**; the margin is given as a percentage of the frame, so
the same choice holds at any resolution, and it goes up to 70% — past the
middle, if that is where the words belong. A margin larger than the frame is
held inside it rather than pushing the words out of the picture.

**Type and size are in the dialog too.** It lists every font this machine can
draw with — scanned rather than guessed, about 365 of them here, with Apple's
internal fallback faces left out — and takes a `.ttf`, `.otf` or `.ttc` dropped
in. Size is a multiple of what the preset already looks right at, so it survives
changing resolution. A font in the working folder wins over the system's copy of
the same family, since that is the one you put there on purpose.

**The ball tab decides what bounces**: a circle, a PNG of your own, or nothing
at all. The circle has a colour and a size — a multiple of what it would have
been, which is a quarter of the text height, so the choice still holds when the
text size or the preset changes. Choosing the circle again after a PNG takes
the PNG out of `videokar.toml` rather than leaving it there to be ignored.

**The dialog remembers.** Rendering writes the choices to `videokar.toml` in the
working folder and the dialog restores them next time — from the folder, not
from the browser, so it survives a reload, another machine, and being edited by
hand. It is the same file `videokar render -c` reads, so anything set in the
view can be rendered from a terminal.

A local page on `127.0.0.1:8712` with the waveform of the **isolated vocal**
behind the lines — the point being that you can see where a phrase actually
starts instead of guessing at it. Drag a line to move it, drag a word to nudge
it, drag a word's left or right edge to change how long it lasts, double-click a
word to retype one the aligner misheard, and double-click a line — its label, or
its row in the list — to retype the whole thing when the wording is wrong rather
than a single word.

Retyping a line can change how many words it has. Rather than spreading them
evenly and throwing away everything that was already right, the old and new
wordings are matched up: a word still there keeps its timing, and only the ones
that changed are fitted between their neighbours. Fixing a typo therefore costs
nothing.

A song can be taken out of the folder with the ✕ beside it, which turns the row
into a question rather than opening a browser dialog. It moves to a `.trash`
subfolder rather than being deleted — it is somebody's work, the button is one
click, and the audio it names is left alone. Space plays, arrows
scrub, clicking the waveform seeks.

Every edit goes through the same operations `videokar fix` uses, so pinning and
the ripple behave identically whether you drag or type a command, and an edit
that would invert the timeline comes back as a message rather than being
written. The file on disk is rewritten after each accepted edit — there is no
save button and nothing to lose — and ⌘Z steps back through the last fifty.

It reads and writes a file on your machine and has no authentication, so it
binds to localhost and should stay there. If the page shows a red band and says
the server is not answering, `videokar serve` has stopped — nothing is lost, the
document on disk is always current.

## Fixing a drifting block

Alignment on sung audio drifts in blocks, not in single words: a whole chorus
lands three seconds early while the lines on either side are right. So `fix`
moves a line and carries the lines after it — but stops at the next line you
have **pinned**, because a plain forward ripple would push the already-correct
lines out of place to rescue the wrong ones.

```bash
videokar fix list song.json --flagged      # which lines, and their ids
videokar fix pin  song.json -l l13 -l l14  # these two are right: do not move them
videokar fix shift song.json --line l11 --to 56.30
videokar fix stretch song.json --from l9 --to l10 --start 50.1 --end 56.2
videokar check song.json
videokar render song.json -o overlay.mov   # no re-alignment
```

| operation | what it does |
| --- | --- |
| `list` | line ids, timings, pins and flags |
| `shift --line L --by ±S` / `--to T` | move a line, rippling up to the next pin |
| `stretch --from A --to B --start S --end E` | fit a run of lines into an exact span |
| `text --line L "the line as it should read"` | retype a whole line |
| `word --id L.wN --by ±S` / `--to T` | move one word, leaving its neighbours |
| `pin --line L` | declare a timing correct; `--undo` to release it |
| `mute --line L` | keep a line in the file but out of the video |

Every operation refuses an edit that would invert the timeline rather than
writing it, `--dry-run` shows the result without saving, and edited words are
marked `manual` so a re-align leaves them alone.

```bash
videokar align song.mp3 --lyrics song.txt -o song.json
videokar check song.json
videokar render song.json -o overlay.mov
```

## Output

| `--format` | what you get |
| --- | --- |
| `prores4444` (default) | `.mov` with alpha — what an editor expects, and enormous |
| `png_mov` | `.mov` with alpha, lossless, a fraction of the size |
| `animation` | `.mov` with alpha, lossless, smaller still on flat lyrics |
| `mp4` | H.264 on an opaque background, audio muxed in |
| `png` | numbered frames with alpha, for anything else |

ProRes 4444 is a mastering codec: at 1080p25 it costs around 90 Mbit/s whatever
you put in it, and flat colour over a transparent field is the worst case for an
intra-frame DCT codec. The other two are lossless and carry alpha just as well —
the same four-minute 1080p overlay came to 0.94 GB as ProRes and 0.15 GB as
animation, decoding no slower. ProRes stays the default because it is what an
editor is tuned for.

**Render at your editing timeline's frame rate.** A clip at a rate the project
does not use gets conformed, and a conform reads exactly like the overlay
starting almost right and falling further behind as the song goes on — 25fps
stretched to 24 puts it seven seconds late by the three minute mark. The NTSC
rates are understood as the fractions they actually are: `--fps 23.976` encodes
at 24000/1001, not at the decimal, which would put a smaller drift back.

The overlay carries the song by default. A clip holding its own audio lines
itself up in an editor and cannot drift away from it; mute or detach the track
once it is in place, or pass `--no-audio` if you would rather it did not.

Long renders go out in segments and are concatenated with a stream copy, so a
three minute track never depends on one ffmpeg process staying alive for three
minutes. Frame times come from the absolute frame index rather than accumulating
per segment, so a seam cannot drift the timing.

## Configuration

```bash
videokar config presets              # what is built in
videokar config init --preset alpha  # a file to edit, every setting explained
videokar render song.json -c videokar.toml
```

| preset | what it is for |
| --- | --- |
| `alpha` | transparent ProRes 4444 overlay for an editor |
| `youtube` | finished 1080p mp4 on its own background |
| `shorts` | vertical 1080x1920, centred, larger text |
| `minimal` | text only — no outline, no ball, hard cuts |

Layers resolve in order: built-in defaults, then a preset, then your file, then
command-line flags. Merging is per key rather than per section, so setting one
colour does not quietly reset the block around it. A file can name the preset it
builds on with `preset = "youtube"` at the top.

Colours are `#rrggbb` or `#rrggbbaa`.

**Every measurement defaults to a fraction of the frame**, not to a pixel count:
font size, margins, outline width, and the ball's radius, arc and clearance. A
preset therefore looks the same at 320x180 and at 4K, and setting any of them
explicitly still wins. Fixed pixels were fine until the first small render — at
320x180 the old 96px margin left 96px of usable width, wrapping every line into
three, and the ball's arc put it eighty pixels above the top of the picture.

The font size is still one fixed size per render: what scales is the default, not
the text within a video.

The settings are a typed schema, not a free-form file: `videokar config show
--schema` prints it, bounds and choices included. That is deliberate — it is
what will let the sync view build its own controls from the same definitions
rather than a hand-written form that drifts out of step.

**The ball is drawn smoothly.** Pillow's ellipse has no anti-aliasing and rounds
to whole pixels, so the old ball was a hard-edged disc that jumped a pixel at a
time — measured on the reference track it was exactly 33x33 in every frame while
the position it was asked for moved in fractions, and at speed the sliding
stair-steps read as the shape wobbling. It is now supersampled and placed to a
fraction of a pixel.

If you liked the wobble, `[ball] squash = 0.3` gives you it on purpose: the ball
stretches along its direction of travel and squashes across it, keeping its area
so it never appears to change size.

**The ball can be a PNG.** Anything with transparency — a cotton tuft, a paw, a
logo. It is measured on what is actually drawn rather than on the file's canvas,
so an export with transparent margins comes out the size you asked for instead
of quietly smaller, and it lands on exactly the point the circle would have.

```bash
videokar render song.json --sprite paw.png --sprite-scale 2
```

`assets/sprites/cotton.png` is there to try it with. In the sync view, the
export dialog lists the PNGs in the folder and takes new ones — and picking the
circle again puts the sprite back down.

The circle has settings of its own: `[ball] colour` and `radius`, both in the
dialog. `kind = "none"` draws nothing at all, for when the words are enough.

## Something behind the words

A still or a clip, for when the video is the finished thing rather than an
overlay to drop onto something else.

```bash
videokar render song.json --behind photo.jpg --dim 0.4
videokar render song.json --behind loop.mp4
```

The suffix decides which it is. A still is fitted and darkened once and every
frame starts from it; a clip is composited by ffmpeg while encoding, because
ffmpeg is already in the pipeline and pulling video frames into Pillow one at a
time would be the slow way round.

```toml
[background]
image = "photo.jpg"   # or video = "loop.mp4", never both
loop = true           # repeat a clip shorter than the song
fit = "cover"         # cover crops, contain pads, stretch distorts
dim = 0.35            # darken it so the words stay readable
```

A clip shorter than the song repeats, and keeps repeating across a segment
boundary rather than restarting at it — the offset is taken with ffmpeg's
`trim` rather than by seeking, because seeking into a stream that is also being
looped does not land where the arithmetic says, and the drift only shows up
minutes in.

A background and a transparent export contradict each other, so `alpha` with
either one is refused before the render rather than after it. Use `youtube`,
`shorts`, or `--opaque`.

In the sync view it is the **Behind** tab: it lists the pictures and clips in
the folder, says which each one is, and takes new ones. The preview shows it —
for a clip, the frame it would be showing at that point in the song, so the
still in the dialog is not quietly lying about what the render will produce.

```bash
videokar sprite paw.png --scale 3
```

says what it is and how it will come out — canvas, the part actually drawn, the
pixel size at your output, and whether it has an alpha channel at all. Size is
rarely the problem: it is scaled down, and 32 pixels is a default ball at 1080p.
A flattened export with no transparency is the problem, and looks like a solid
rectangle bouncing over the words.

**The ball bounces on beats, not on words.** Sung words run together — on the
reference track 41% of the gaps between words are under a third of a second and
the quickest, "I" to "know", is 20ms, half a frame at 25fps. A full arc in that
time is a vertical twitch. Words closer together than `min_bounce` share one
bounce, landing over the middle of the group, so every hop lasts long enough to
read as a bounce.

**Colour, outline and shadow are in the export dialog**, because on a busy clip
the words that have not been sung yet are the first thing to disappear. An
outline thickens every letter and starts closing up the counters at small sizes;
a shadow lifts the text off the picture without touching its shape. They work
together, and both are off or on independently.

```toml
[main]
colour_on = "#ffeebe"
colour_off = "#9695b4"
outline = "#000000d2"
outline_width = 3

[shadow]
colour = "#000000c8"   # empty draws none
```

The shadow is drawn once per line rather than once per frame — its shape does
not change while the line is up, only the colour of the words above it — which
costs a millisecond a frame instead of a blur every time.

**Text is one size for the whole video.** A line too wide for the frame wraps
onto two rows rather than being drawn smaller than the line before it. If you
would rather it shrank, `--min-scale 0.7` allows that explicitly. The second
voice — the parenthesised lines — is styled separately on purpose, and is
smaller by default.

## The pivot format

`song.json` is the document everything else works from — alignment writes it,
`check` reads it, `fix` edits it, the renderer draws from it. It holds timing
and structure and nothing about appearance, so restyling never costs another
alignment run and re-aligning never loses your styling.

It is meant to be edited by hand, so words and vocal regions each stay on one
line: a word is a row you can scan, and correcting one is a one-line diff.

```json
{
 "id": "l11", "text": "Two purrs and then she's gone",
 "voice": "main", "direction": "higher harmony",
 "start": 52.02, "end": 54.74, "score": 0.0143,
 "flags": ["low_score"], "sung": true, "pinned": false,
 "words": [
  {"id": "l11.w0", "text": "Two", "norm": "two", "start": 52.02, "end": 52.28, "score": 0.02, "manual": false}
 ]
}
```

Editing rules, because alignment gets words wrong as well as times:

* **The `words` list is the truth.** The renderer draws words, never `line.text`.
  Correct a misheard word there and it is already fixed on screen.
* `line.text` is a readable copy. Editing a word leaves it out of date; `check`
  says so and nothing breaks.
* `norm` is what the aligner was given, derived from `text`. Editing `text`
  leaves it stale; `check` says so and re-aligning recomputes it.
* `sung: false` keeps a line in the file but out of the video — for a lyric that
  never made the recording.
* `pinned: true` means *this timing is correct*. It exists for `fix`: shifting a
  line carries the lines after it, but the shift stops at the next pinned line
  and is redistributed within that span. Without anchors, correcting a drifting
  block would push the already-correct lines after it out of place.

## When the alignment is wrong

It sometimes will be. A forced aligner has to place every word somewhere, so
lyrics that do not quite match the recording — a repeat Suno sang but did not
write down, an ad-lib, a line that never made the final mix — come back as
confident-looking nonsense rather than an error.

videokar scores every line and flags the ones whose *shape* does not look like
singing: words smeared across an instrumental break, a line crammed into no
time at all, a long silence mid-phrase, words placed where the vocal stem says
nobody is singing. Raw model scores are not usable as an absolute threshold on
sung audio — the median per-character probability on a real track sits near 0.2
— so the score check is relative to the track's own median and the structural
checks carry most of the weight.

The workflow that follows from this is deliberate: align once, look at what got
flagged, correct it with `fix`, and re-render without re-aligning.

One check is worth calling out. A line can be simply half a second late: an
ordinary shape, an ordinary score, sitting well inside a vocal region — nothing
about it looks wrong, and you only find it by watching the video. So the vocal
attacks are found in the stem and each line's start is measured against the
nearest one. `check` reports the distance and flags the lines whose distance is
an outlier for that song. On the reference track it surfaced four lines that
everything else called clean.

Pinning a line drops its low-score flag. That flag is the model's opinion of its
own confidence, and pinning is you overruling it — leaving it up would bury the
lines still worth a look under the ones already dealt with.

## Devices

On Apple Silicon the acoustic models run on the GPU and the Viterbi pass does
not: `torchaudio`'s `forced_align` has no MPS kernel, so it always falls back to
the CPU. videokar splits the work accordingly instead of making you pick. Pass
`--device cpu` to force everything onto the CPU.

## Cache

Separation is the expensive stage and depends only on the audio, so the isolated
vocal is cached under `~/Library/Caches/videokar/` keyed by a hash of the file
contents — rename or move the track and it still hits. Override the location
with `VIDEOKAR_CACHE_DIR`.

```bash
videokar lyrics examples/ladycat/lyrics.txt
videokar lyrics examples/ladycat/lyrics.txt --json
```

## Example

`examples/ladycat/` carries the lyrics and config for the track this tool was
built against. The audio itself (`ladycat.mp3`) is the author's own and is not
distributed with the repo — drop your own mp3 there to run the integration
tests, or they skip.

## Development

```bash
uv sync --extra web --group dev
uv run pytest
uv run ruff check .
```

CI runs both on Linux and macOS, with ffmpeg installed so the encoder is
actually exercised, and fails if anything in the non-integration set *skips* —
a test that quietly stopped running is worse than one that fails. The
integration tests need the align extra and the author's own audio, so they are
not run there.

```
src/videokar/
  lyrics/       parsing a Suno export, and normalising for the aligner
  audio/        separation, peaks, voice activity
  align/        forced alignment and the confidence flags
  project/      the pivot document: model, edits, checks, i/o
  config/       the style schema, presets, and how they resolve
  render/       frames, ball, fonts, sprites, encoding
  cli/          one module per command
  web/          the sync view: routes/ per area, static/js/ per concern
  pipeline.py   the stages, strung together
  cache.py      keyed on file content, so a rename still hits
  transcribe/   empty: making lyrics from the audio is not built yet
```

`docs/prototype/` keeps the original throwaway scripts and the notes that
started this project. They are reference material, not part of the package.

## License

MIT — see [LICENSE](LICENSE).
