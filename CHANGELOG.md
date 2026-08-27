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

### Changed

- Square-bracket tags are now split two ways: a tag naming a song section
  (`[Chorus - wide, stacked harmonies]`, `[Fade-Outro]`) opens a section, while
  a performance direction (`[higher harmony]`, `[all voices]`) is carried on the
  lines that follow it. Previously every tag opened a section, which chopped a
  chorus into three.
- `videokar lyrics` prints sections as headers rather than as a column, so a
  long tag no longer wraps every line of the song, and shows empty sections and
  directions.
