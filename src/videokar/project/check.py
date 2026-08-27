"""Re-examine a pivot document and say what looks wrong.

Flags are recomputed from the document rather than read back from what
alignment wrote, so `check` tells the truth after a `fix` as well as after an
`align`. On top of the alignment-shape checks it verifies the things hand
editing can break: a line whose text no longer matches its words, a word whose
aligner form was left behind when its text changed, timings that run backwards.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..align.base import WordTiming
from ..align.confidence import LineReport, analyse
from ..audio.vad import Region
from .model import Song

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Issue:
    level: str
    code: str
    message: str
    line_id: str | None = None


@dataclass(slots=True)
class SongReport:
    reports: list[LineReport] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    line_ids: list[str] = field(default_factory=list)
    """Line id per report index, so a report can be named in the output."""

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == ERROR]

    @property
    def suspicious_line_ids(self) -> list[str]:
        return [self.line_ids[r.index] for r in self.reports if r.suspicious]

    @property
    def ok(self) -> bool:
        return not self.issues and not any(r.suspicious for r in self.reports)


def _timings(song: Song) -> list[WordTiming]:
    timings: list[WordTiming] = []
    for group, line in enumerate(song.lines):
        if not line.sung:
            continue
        for word in line.words:
            if word.timed:
                timings.append(
                    WordTiming(
                        index=len(timings),
                        group=group,
                        word=word.text,
                        start=word.start,
                        end=word.end,
                        score=word.score if word.score is not None else 0.0,
                    )
                )
    return timings


def check_song(song: Song, *, apply: bool = False) -> SongReport:
    """Recompute line flags and look for hand-editing damage.

    With `apply`, the freshly computed flags are written back onto the document.
    """
    lines = song.lines
    report = SongReport(line_ids=[line.id for line in lines])

    timings = _timings(song)
    regions = [Region(start, end) for start, end in song.vocal_regions]
    report.reports = analyse(
        timings,
        group_count=len(lines),
        regions=regions,
        # A pinned line has been listened to and declared right, so the model's
        # opinion of its own confidence is no longer news.
        adjudicated=[index for index, line in enumerate(lines) if line.pinned],
    )

    if apply:
        by_index = {r.index: r for r in report.reports}
        for index, line in enumerate(lines):
            found = by_index.get(index)
            line.flags = [str(flag) for flag in found.flags] if found else []
            line.score = found.score if found else None

    for line in lines:
        if line.text_is_stale:
            report.issues.append(
                Issue(
                    WARNING,
                    "stale_line_text",
                    f"line text {line.text!r} no longer matches its words "
                    f"{line.words_text!r} — the renderer draws the words",
                    line.id,
                )
            )
        if line.sung and not line.timed_words:
            report.issues.append(
                Issue(
                    ERROR,
                    "untimed_line",
                    "marked as sung but has no timed words — "
                    "re-align, or mark it unsung with 'fix mute'",
                    line.id,
                )
            )
        for word in line.words:
            if word.timed and word.start >= word.end:
                report.issues.append(
                    Issue(
                        ERROR,
                        "backwards_word",
                        f"{word.id} ends at {word.end} but starts at {word.start}",
                        line.id,
                    )
                )
            if word.norm_is_stale(song.align.language):
                report.issues.append(
                    Issue(
                        WARNING,
                        "stale_norm",
                        f"{word.id} text {word.text!r} was edited but its aligner form is "
                        f"still {word.norm!r} — re-align to recompute it",
                        line.id,
                    )
                )

    previous = None
    for line in lines:
        if line.start is None:
            continue
        if previous is not None and line.start < previous.end - 1e-6:
            report.issues.append(
                Issue(
                    WARNING,
                    "out_of_order",
                    f"starts at {line.start} before {previous.id} ends at {previous.end}",
                    line.id,
                )
            )
        previous = line

    return report
