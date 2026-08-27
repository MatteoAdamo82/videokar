"""Tell the user which lines to go and look at.

Forced alignment never fails loudly: hand it a lyric the singer never sang and
it will still return a start and an end for every word. The failure shows up as
a shape — six words smeared over eleven seconds, a chorus crammed into two, a
line placed where the vocal track is silent — so that is what gets checked here.

Raw CTC scores are not usable as an absolute threshold on singing. On the
reference track the *median* per-character probability is around 0.19; a fixed
"below 0.5 is bad" rule would condemn the whole song. So the score check is
relative to the track's own median, and the structural checks below carry most
of the weight.

A line the user has pinned is one they have listened to and declared right. The
score flag is an opinion about how sure the model was, and a person has now
overruled it, so it is dropped for those lines — five of the eight flags on the
reference track were on lines already fixed by hand, which is exactly the noise
that hides the three still worth looking at. The structural flags stay: those
describe the shape of what is in the file now, not a guess about it.
"""

from __future__ import annotations

import statistics
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from ..audio.vad import Region, in_any_region
from .base import WordTiming


class Flag(StrEnum):
    """Why a line is worth a second look."""

    LOW_SCORE = "low_score"
    """The acoustic model was unusually unsure, for this track."""

    SMEARED = "smeared"
    """Too few words for the time they occupy — the classic instrumental-gap
    failure, where a line gets stretched across a break it was never sung in."""

    CRAMMED = "crammed"
    """Too many words for the time they occupy. Usually the other half of a
    smear: whatever the stretched line stole, the next lines have to fit in."""

    INTERNAL_GAP = "internal_gap"
    """A long silence inside one line, where a singer would not have stopped."""

    OUTSIDE_VOCAL = "outside_vocal"
    """Placed where the vocal stem says nobody is singing."""

    OVERLAPS_NEXT = "overlaps_next"
    """Ends after the following line starts."""


# Sung word rates on the reference track sit between roughly 1.5 and 6 words per
# second. These bounds are deliberately outside that: they are meant to catch
# alignment failures, not unusual phrasing.
MIN_RATE = 0.8
MAX_RATE = 8.0
MAX_INTERNAL_GAP = 1.5
SCORE_RATIO = 0.4
MIN_DURATION_FOR_RATE = 0.8
VOCAL_TOLERANCE = 0.25


@dataclass(slots=True)
class LineReport:
    """Alignment diagnostics for one line."""

    index: int
    start: float
    end: float
    word_count: int
    score: float
    rate: float
    """Words per second."""

    max_internal_gap: float
    outside_fraction: float
    flags: list[Flag] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def suspicious(self) -> bool:
        return bool(self.flags)


def group_words(words: Sequence[WordTiming], group_count: int) -> list[list[WordTiming]]:
    """Split a flat timing list back into its groups, keeping empty ones."""
    grouped: list[list[WordTiming]] = [[] for _ in range(group_count)]
    for word in words:
        grouped[word.group].append(word)
    return grouped


def analyse(
    words: Sequence[WordTiming],
    *,
    group_count: int,
    regions: Sequence[Region] = (),
    adjudicated: Collection[int] = (),
) -> list[LineReport]:
    """Score every line and flag the ones that do not look like singing.

    `adjudicated` holds the indices of lines a person has declared correct.
    Those keep their score but lose the low-score flag.
    """
    grouped = group_words(words, group_count)
    scores = [w.score for w in words]
    median = statistics.median(scores) if scores else 0.0
    score_floor = median * SCORE_RATIO

    reports: list[LineReport] = []
    for index, group in enumerate(grouped):
        if not group:
            continue
        start, end = group[0].start, group[-1].end
        duration = end - start
        gaps = [b.start - a.end for a, b in zip(group, group[1:], strict=False)]
        outside = (
            sum(not in_any_region(w.start, list(regions), tolerance=VOCAL_TOLERANCE) for w in group)
            / len(group)
            if regions
            else 0.0
        )
        reports.append(
            LineReport(
                index=index,
                start=start,
                end=end,
                word_count=len(group),
                score=round(sum(w.score for w in group) / len(group), 4),
                rate=round(len(group) / duration, 2) if duration > 0 else 0.0,
                max_internal_gap=round(max(gaps), 3) if gaps else 0.0,
                outside_fraction=round(outside, 3),
            )
        )

    settled = set(adjudicated)
    for report, following in zip(reports, reports[1:] + [None], strict=False):
        if report.score < score_floor and report.index not in settled:
            report.flags.append(Flag.LOW_SCORE)
        # A two-word line is over in a moment; judging its rate says more about
        # rounding than about the alignment.
        if report.duration >= MIN_DURATION_FOR_RATE:
            if report.rate < MIN_RATE:
                report.flags.append(Flag.SMEARED)
            elif report.rate > MAX_RATE:
                report.flags.append(Flag.CRAMMED)
        if report.max_internal_gap > MAX_INTERNAL_GAP:
            report.flags.append(Flag.INTERNAL_GAP)
        if report.outside_fraction > 0.5:
            report.flags.append(Flag.OUTSIDE_VOCAL)
        if following is not None and report.end > following.start + 1e-6:
            report.flags.append(Flag.OVERLAPS_NEXT)

    return reports
