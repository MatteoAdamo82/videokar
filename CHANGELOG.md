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

### Fixed

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
