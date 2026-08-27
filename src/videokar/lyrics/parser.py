"""Parse Suno-style lyrics into sections, lines and alignable tokens.

Input conventions, all optional:

    [Verse 1]                     section tag — kept in the output, never aligned
    Seven o'clock, she's at the door
    (she's not mine, I know)      a fully parenthesised line is the second voice

Everything else is a plain lyric line. Blank lines are ignored. Lines that
appear before the first tag land in a leading section whose tag is None.

The parser guarantees a 1:1 mapping between the tokens it emits and the words
the aligner will time, which is what lets the renderer draw token *i* under
word *i* without an assertion at draw time.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .normalize import normalize_token

Voice = Literal["main", "paren"]

_SECTION_RE = re.compile(r"^\[\s*([^\[\]]+?)\s*\]$")


def _unwrap_parens(text: str) -> str | None:
    """Return the inside of a fully parenthesised line, else None.

    Depth counting rather than a regex, so a mixed line like
    ``(one) and (two)`` stays a main-voice line instead of being read as
    one big parenthesis.
    """
    if not (text.startswith("(") and text.endswith(")")):
        return None
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and index != len(text) - 1:
                return None
    if depth != 0:
        return None
    return text[1:-1].strip() or None


@dataclass(slots=True)
class Token:
    """One whitespace-delimited chunk of a line."""

    text: str
    """As written, punctuation and capitals intact. This is what gets drawn."""

    norm: str | None
    """Aligner form, or None when the token has nothing to align against."""

    @property
    def alignable(self) -> bool:
        return self.norm is not None


@dataclass(slots=True)
class ParsedLine:
    id: str
    text: str
    """Visible text. For a `paren` line the outer parentheses are stripped;
    `voice` records where they came from so the renderer can put them back."""

    voice: Voice
    tokens: list[Token]
    source_line: int
    """1-based line number in the source file, for error messages."""

    @property
    def alignable_tokens(self) -> list[Token]:
        return [t for t in self.tokens if t.alignable]

    @property
    def is_alignable(self) -> bool:
        return any(t.alignable for t in self.tokens)


@dataclass(slots=True)
class ParsedSection:
    id: str
    tag: str | None
    lines: list[ParsedLine] = field(default_factory=list)


@dataclass(slots=True)
class ParsedLyrics:
    sections: list[ParsedSection] = field(default_factory=list)
    language: str = "en"

    @property
    def lines(self) -> list[ParsedLine]:
        return [line for section in self.sections for line in section.lines]

    @property
    def alignable_words(self) -> list[str]:
        """Flat transcript handed to the aligner, in singing order."""
        return [word for group in self.word_groups for word in group]

    @property
    def word_groups(self) -> list[list[str]]:
        """One group of aligner words per line, in singing order.

        Lines with nothing alignable still produce an empty group, so a group
        index is always a line index.
        """
        return [[t.norm for t in line.alignable_tokens if t.norm] for line in self.lines]

    def iter_tokens(self) -> Iterator[tuple[ParsedLine, Token]]:
        for line in self.lines:
            for token in line.tokens:
                yield line, token

    def __len__(self) -> int:
        return len(self.lines)


class LyricsError(ValueError):
    """The lyrics file cannot be parsed into anything alignable."""


def parse_lyrics(text: str, *, language: str = "en") -> ParsedLyrics:
    """Parse the contents of a lyrics file."""
    text = unicodedata.normalize("NFC", text.lstrip("﻿"))
    parsed = ParsedLyrics(language=language)
    current: ParsedSection | None = None
    line_index = 0

    for source_line, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue

        section_match = _SECTION_RE.match(stripped)
        if section_match:
            current = ParsedSection(id=f"s{len(parsed.sections)}", tag=section_match.group(1))
            parsed.sections.append(current)
            continue

        if current is None:
            current = ParsedSection(id=f"s{len(parsed.sections)}", tag=None)
            parsed.sections.append(current)

        voice: Voice = "main"
        body = stripped
        inner = _unwrap_parens(stripped)
        if inner is not None:
            voice = "paren"
            body = inner

        line_id = f"l{line_index}"
        current.lines.append(
            ParsedLine(
                id=line_id,
                text=body,
                voice=voice,
                tokens=[
                    Token(text=chunk, norm=normalize_token(chunk, lang=language))
                    for chunk in body.split()
                ],
                source_line=source_line,
            )
        )
        line_index += 1

    if not parsed.alignable_words:
        raise LyricsError("no alignable words found — is the file empty or all section tags?")
    return parsed


def parse_lyrics_file(path: str | Path, *, language: str = "en") -> ParsedLyrics:
    """Read and parse a lyrics file (UTF-8, tolerant of a BOM and CRLF)."""
    return parse_lyrics(Path(path).read_text(encoding="utf-8"), language=language)
