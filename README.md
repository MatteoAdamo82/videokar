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

More commands land with their pipeline stage: `align`, `check`, `fix`,
`render`, `preview`, `build`, `transcribe`, `config`, `cache`.

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
