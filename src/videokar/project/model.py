"""The pivot format: what videokar knows about when each word is sung.

This is the one file the whole tool revolves around. Alignment writes it,
`check` reads it, `fix` edits it, and the renderer draws from it. It holds
timing and structure and nothing about appearance — colours, fonts and the
bouncing ball live in the config — so restyling a video never costs another
alignment run, and re-aligning never loses your styling.

It is also meant to be opened in an editor and corrected by hand, which is why
ids are short and stable and the numbers are plain seconds. Alignment gets words
wrong as well as times — a misheard word, a lyric that differs from what was
actually sung — so word text is editable too, and the rules for that are:

* The `words` list is the truth. The renderer draws words, never `line.text`.
* `line.text` is a convenience for reading the file and for `check` output. Edit
  a word and it goes out of date; `check` says so, and nothing breaks.
* `norm` is a cache of what the aligner was given, derived from `text`. Editing
  `text` leaves it stale; `check` says so, and re-aligning recomputes it.

So the safe edit is: change `text` on the word, leave `norm` alone, and re-run
`check`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .. import __version__
from ..lyrics.normalize import normalize_token

SCHEMA_VERSION = 1

Voice = Literal["main", "paren"]


class Base(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class Word(Base):
    id: str
    text: str
    """As written, punctuation and capitals intact. This is what gets drawn."""

    norm: str | None = None
    """What the aligner was given, derived from `text`. None means the token had
    nothing to align — punctuation on its own. Goes stale if you edit `text`;
    `check` reports that and re-aligning recomputes it."""

    start: float | None = None
    end: float | None = None
    score: float | None = None
    """Mean per-character probability, 0..1. Low means the aligner was guessing.

    Not comparable between tracks: on sung audio a whole song can sit near 0.2.
    """

    manual: bool = False
    """Set by hand. Re-aligning leaves it alone unless forced."""

    @property
    def timed(self) -> bool:
        return self.start is not None and self.end is not None

    def norm_is_stale(self, language: str = "en") -> bool:
        """True when `text` has been edited without `norm` following."""
        return self.norm != normalize_token(self.text, lang=language)


class Line(Base):
    id: str
    text: str
    """Human-readable copy of the line, for reading the file and for `check`.

    The renderer draws `words`, not this. Editing a word's text leaves this out
    of date, which `check` reports and nothing else depends on.
    """

    voice: Voice = "main"
    direction: str | None = None
    """Performance direction in force, e.g. "higher harmony"."""

    start: float | None = None
    end: float | None = None
    score: float | None = None
    flags: list[str] = Field(default_factory=list)
    """Why this line is worth a second look. Written by `check`."""

    sung: bool = True
    """False for a line that is in the lyrics but not in the recording. It keeps
    its place in the file, gets no timing, and is skipped by the renderer."""

    pinned: bool = False
    """This timing is correct — treat it as an anchor.

    `fix` shifts a line and carries the lines after it, but a shift stops at the
    next pinned line and is redistributed within that span. Without anchors,
    correcting a drifting block would push the already-correct lines after it
    out of place.
    """

    words: list[Word] = Field(default_factory=list)

    @property
    def timed_words(self) -> list[Word]:
        return [w for w in self.words if w.timed]

    @property
    def words_text(self) -> str:
        """The line as its words actually spell it."""
        return " ".join(word.text for word in self.words)

    @property
    def text_is_stale(self) -> bool:
        return self.text != self.words_text

    def rebuild_text(self) -> None:
        self.text = self.words_text

    @property
    def duration(self) -> float | None:
        if self.start is None or self.end is None:
            return None
        return self.end - self.start


class Section(Base):
    id: str
    tag: str | None = None
    start: float | None = None
    end: float | None = None
    lines: list[Line] = Field(default_factory=list)


class AudioRef(Base):
    path: str
    """As given on the command line. Relative paths resolve against the JSON."""

    sha256: str
    duration: float
    sample_rate: int
    channels: int


class AlignInfo(Base):
    model: str
    device: str
    separator: str | None = None
    """Separation model, or None when alignment ran against the full mix."""

    language: str = "en"
    frame_duration: float | None = None
    created_at: str | None = None
    elapsed: float | None = None


class Song(Base):
    schema_version: Annotated[int, Field(alias="schema")] = SCHEMA_VERSION
    videokar_version: str = __version__
    audio: AudioRef
    align: AlignInfo
    vocal_regions: list[tuple[float, float]] = Field(default_factory=list)
    """Where the vocal stem says someone is singing. Constrains nothing on its
    own; `check` uses it to spot words placed in an instrumental break."""

    sections: list[Section] = Field(default_factory=list)

    @property
    def lines(self) -> list[Line]:
        return [line for section in self.sections for line in section.lines]

    @property
    def words(self) -> list[Word]:
        return [word for line in self.lines for word in line.words]

    def line(self, line_id: str) -> Line:
        for line in self.lines:
            if line.id == line_id:
                return line
        raise KeyError(f"no line {line_id!r} — ids look like 'l12'")

    def word(self, word_id: str) -> Word:
        for word in self.words:
            if word.id == word_id:
                return word
        raise KeyError(f"no word {word_id!r} — ids look like 'l12.w3'")

    def section_of(self, line_id: str) -> Section:
        for section in self.sections:
            if any(line.id == line_id for line in section.lines):
                return section
        raise KeyError(f"no line {line_id!r}")

    def refresh_bounds(self) -> None:
        """Recompute line and section spans from the words underneath them.

        Called after any edit: a line's start is its first timed word and a
        section's is its first timed line, so nothing can drift out of step with
        what it contains.
        """
        for section in self.sections:
            for line in section.lines:
                timed = line.timed_words
                if not timed or not line.sung:
                    line.start = line.end = None
                    continue
                line.start = min(w.start for w in timed)
                line.end = max(w.end for w in timed)
            spans = [(ln.start, ln.end) for ln in section.lines if ln.start is not None]
            section.start = min(s for s, _ in spans) if spans else None
            section.end = max(e for _, e in spans) if spans else None
