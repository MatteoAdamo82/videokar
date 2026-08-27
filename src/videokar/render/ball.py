"""The bouncing ball.

One arc per beat rather than per word. The ball leaves the word being sung and
lands on the next target as it starts, so it arrives on the beat rather than
chasing it. Between lines it does not travel — it fades out with the old line
and runs in again ahead of the new one, because a ball sliding across the frame
during eight bars of guitar reads as a bug.

Targets are not always single words. Sung words run together: on the reference
track 41% of the hops are under a third of a second and the quickest, "I" to
"know", is 20ms — half a frame at 25fps. An arc squeezed into that reads as a
twitch. Words closer together than `min_bounce` therefore share one bounce,
which lands over the middle of the group, and grouping guarantees every hop
lasts at least that long without any special-casing further down.
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


@dataclass(frozen=True, slots=True)
class Bounce:
    """One landing: a word, or a run of words too quick to visit separately."""

    centre_x: float
    y: float
    width: float
    start: float
    end: float
    words: int


def bounce_targets(placed: list[PlacedWord], min_bounce: float) -> list[Bounce]:
    """Group words into the places the ball actually lands."""
    timed = [word for word in placed if word.word.timed]
    if not timed:
        return []

    groups: list[list[PlacedWord]] = [[timed[0]]]
    for word in timed[1:]:
        head = groups[-1][0]
        # A wrapped line puts the next word on another row; landing between two
        # rows would look like a miss, so a row change always starts a group.
        same_row = word.y == head.y
        if same_row and word.word.start - head.word.start < min_bounce:
            groups[-1].append(word)
        else:
            groups.append([word])

    bounces = []
    for group in groups:
        left = min(word.x for word in group)
        right = max(word.x + word.width for word in group)
        bounces.append(
            Bounce(
                centre_x=(left + right) / 2,
                y=group[0].y,
                width=right - left,
                start=group[0].word.start,
                end=group[-1].word.end,
                words=len(group),
            )
        )
    return bounces


def _arc(start: Bounce, end: Bounce, progress: float, style: BallStyle) -> BallPosition:
    """Parabola-ish hop between two words, sine rather than a true parabola so
    it leaves and lands flat instead of stabbing at the text."""
    progress = min(max(progress, 0.0), 1.0)
    x = start.centre_x + (end.centre_x - start.centre_x) * progress
    # Targets can be on different rows; the baseline travels with them.
    base = start.y + (end.y - start.y) * progress
    height = math.sin(progress * math.pi) * style.jump_height
    return BallPosition(x, base - style.gap_above_text - height)


def ball_position(time: float, layout: LineLayout, style: BallStyle) -> BallPosition | None:
    """Where the ball is at `time`, or None when it should not be drawn."""
    if style.kind == "none":
        return None
    bounces = bounce_targets(layout.words, style.min_bounce)
    if not bounces:
        return None

    first, last = bounces[0], bounces[-1]

    if time < first.start:
        # Run-in: the ball drops onto the first target from its own width to the
        # left, so the singer can see it coming.
        if time < first.start - style.lead_in:
            return None
        progress = (time - (first.start - style.lead_in)) / style.lead_in
        # Run-in distance follows the text size, so it looks the same at 720p
        # and at 4K.
        entry = Bounce(
            centre_x=first.centre_x - max(first.width, 60.0),
            y=first.y,
            width=first.width,
            start=first.start,
            end=first.start,
            words=0,
        )
        return _arc(entry, first, progress, style)

    for current, following in zip(bounces, bounces[1:], strict=False):
        if not (current.start <= time < following.start):
            continue
        silence = following.start - current.end
        if silence > style.hide_after:
            # A long rest inside one line: sit on the target just sung, vanish,
            # then run in again rather than crawling across the gap.
            if time < current.end + _PARK:
                return BallPosition(current.centre_x, current.y - style.gap_above_text)
            if time < following.start - style.lead_in:
                return None
            progress = (time - (following.start - style.lead_in)) / style.lead_in
            return _arc(current, following, progress, style)
        span = following.start - current.start
        progress = (time - current.start) / span if span > 0 else 1.0
        return _arc(current, following, progress, style)

    return BallPosition(last.centre_x, last.y - style.gap_above_text)
