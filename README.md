# videokar

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
* A line wrapped entirely in round brackets is the second voice: it gets its own
  font, size, colour and position in the config. A line with brackets only in
  part of it (`(one) and (two)`) stays a normal line.

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

More commands land with their pipeline stage: `preview`, `build`, `transcribe`,
`config`, `cache`.

## The sync view

```bash
videokar serve song.json
```

A local page on `127.0.0.1:8712` with the waveform of the **isolated vocal**
behind the lines — the point being that you can see where a phrase actually
starts instead of guessing at it. Drag a line to move it, drag a word to nudge
it, drag a word's left or right edge to change how long it lasts, double-click a
word to retype one the aligner misheard. Space plays, arrows
scrub, clicking the waveform seeks.

Every edit goes through the same operations `videokar fix` uses, so pinning and
the ripple behave identically whether you drag or type a command, and an edit
that would invert the timeline comes back as a message rather than being
written. The file on disk is rewritten after each accepted edit — there is no
save button and nothing to lose — and ⌘Z steps back through the last fifty.

It reads and writes a file on your machine and has no authentication, so it
binds to localhost and should stay there.

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
| `prores4444` (default) | `.mov` with a real alpha channel — drop it straight over a clip in Final Cut |
| `mp4` | H.264 on an opaque background, audio muxed in |
| `png` | numbered frames with alpha, for anything else |

Long renders go out in segments and are concatenated with a stream copy, so a
three minute track never depends on one ffmpeg process staying alive for three
minutes. Frame times come from the absolute frame index rather than accumulating
per segment, so a seam cannot drift the timing.

Styling is currently command-line flags — `--width`, `--height`, `--fps`,
`--font`, `--font-size`, `--min-scale`, `--opaque`. The TOML config with presets
is the next step.

**The ball bounces on beats, not on words.** Sung words run together — on the
reference track 41% of the gaps between words are under a third of a second and
the quickest, "I" to "know", is 20ms, half a frame at 25fps. A full arc in that
time is a vertical twitch. Words closer together than `min_bounce` share one
bounce, landing over the middle of the group, so every hop lasts long enough to
read as a bounce.

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
uv run pytest
uv run ruff check
```

`docs/prototype/` keeps the original throwaway scripts and the notes that
started this project. They are reference material, not part of the package.

## License

MIT — see [LICENSE](LICENSE).
