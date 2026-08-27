"""The bouncing ball.

One arc per word: the ball leaves the word being sung and lands on the next one
as that word starts, so it arrives on the beat rather than chasing it. Between
lines it does not travel — it fades out with the old line and runs in again
ahead of the new one, because a ball sliding across the frame during eight bars
of guitar reads as a bug.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .layout import LineLayout, PlacedWord
from .style import BallStyle

# How much of a long silence is spent parked on the last word before the ball
# disappears, and reappears ahead of the next one.
_PARK = 0.25


@dataclass(frozen=True, slots=True)
class BallPosition:
    x: float
    y: float
    opacity: float = 1.0


def _arc(start: PlacedWord, end: PlacedWord, progress: float, style: BallStyle) -> BallPosition:
    """Parabola-ish hop between two words, sine rather than a true parabola so
    it leaves and lands flat instead of stabbing at the text."""
    progress = min(max(progress, 0.0), 1.0)
    x = start.centre_x + (end.centre_x - start.centre_x) * progress
    # Words can be on different rows; the baseline travels with them.
    base = start.y + (end.y - start.y) * progress
    height = math.sin(progress * math.pi) * style.jump_height
    return BallPosition(x, base - style.gap_above_text - height)


def ball_position(time: float, layout: LineLayout, style: BallStyle) -> BallPosition | None:
    """Where the ball is at `time`, or None when it should not be drawn."""
    if style.kind == "none":
        return None
    timed = [placed for placed in layout.words if placed.word.timed]
    if not timed:
        return None

    first, last = timed[0], timed[-1]

    if time < first.word.start:
        # Run-in: the ball drops onto the first word from a word-width to its
        # left, so the singer can see it coming.
        if time < first.word.start - style.lead_in:
            return None
        progress = (time - (first.word.start - style.lead_in)) / style.lead_in
        entry = PlacedWord(
            text="",
            word=first.word,
            x=first.x - max(first.width, 60.0),
            y=first.y,
            width=first.width,
            height=first.height,
        )
        return _arc(entry, first, progress, style)

    for current, following in zip(timed, timed[1:], strict=False):
        if not (current.word.start <= time < following.word.start):
            continue
        silence = following.word.start - current.word.end
        if silence > style.hide_after:
            # A long rest inside one line: sit on the word just sung, vanish,
            # then run in again rather than crawling across the gap.
            if time < current.word.end + _PARK:
                return BallPosition(current.centre_x, current.y - style.gap_above_text)
            if time < following.word.start - style.lead_in:
                return None
            progress = (time - (following.word.start - style.lead_in)) / style.lead_in
            return _arc(current, following, progress, style)
        span = following.word.start - current.word.start
        progress = (time - current.word.start) / span if span > 0 else 1.0
        return _arc(current, following, progress, style)

    return BallPosition(last.centre_x, last.y - style.gap_above_text)
