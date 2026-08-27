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
