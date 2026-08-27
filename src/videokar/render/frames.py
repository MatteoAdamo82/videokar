"""One frame at a time.

Layouts are built once for the whole song and cached; a frame is a lookup, a
handful of text draws and a circle. That keeps the per-frame cost low enough
that the encoder, not the renderer, is the slow part.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from PIL import Image, ImageDraw

from ..project.model import Line, Song
from .ball import ball_position
from .layout import LineLayout, layout_line
from .style import RGBA, Style


def _fade(colour: RGBA, opacity: float) -> RGBA:
    red, green, blue, alpha = colour
    return (red, green, blue, int(alpha * max(0.0, min(1.0, opacity))))


@dataclass(frozen=True, slots=True)
class Cue:
    """A line and the window it is on screen for."""

    line: Line
    layout: LineLayout
    appears: float
    leaves: float

    def opacity(self, time: float, fade: float) -> float:
        if fade <= 0:
            return 1.0
        if time < self.appears + fade:
            return (time - self.appears) / fade
        if time > self.leaves - fade:
            return (self.leaves - time) / fade
        return 1.0


class FrameRenderer:
    """Draws the karaoke overlay for a song at any point in time."""

    def __init__(self, song: Song, style: Style | None = None) -> None:
        self.song = song
        self.style = style or Style()
        self.cues = self._build_cues()
        self._starts = [cue.appears for cue in self.cues]

    def _build_cues(self) -> list[Cue]:
        timing = self.style.timing
        sung = [
            line
            for line in self.song.lines
            if line.sung and line.start is not None and line.end is not None
        ]
        cues: list[Cue] = []
        for index, line in enumerate(sung):
            appears = line.start - timing.lead_in
            leaves = line.end + timing.hold
            # Never let a line outstay the next one's entrance, or two lines
            # cross-fade on top of each other in the same place.
            if index + 1 < len(sung):
                leaves = min(leaves, sung[index + 1].start - timing.lead_in)
            if index > 0:
                appears = max(appears, cues[-1].leaves)
            if leaves <= appears:
                leaves = appears + 1e-3
            cues.append(
                Cue(
                    line=line,
                    layout=layout_line(
                        line,
                        self.style.voice_style(line.voice),
                        self.style.layout,
                        self.style.output,
                    ),
                    appears=appears,
                    leaves=leaves,
                )
            )
        return cues

    def cue_at(self, time: float) -> Cue | None:
        index = bisect_right(self._starts, time) - 1
        if index < 0:
            return None
        cue = self.cues[index]
        return cue if time < cue.leaves else None

    def frame(self, time: float) -> Image.Image:
        output = self.style.output
        image = Image.new("RGBA", (output.width, output.height), output.background)
        cue = self.cue_at(time)
        if cue is None:
            return image

        draw = ImageDraw.Draw(image)
        opacity = cue.opacity(time, self.style.timing.fade)
        text_style = cue.layout.style

        for placed in cue.layout.words:
            word = placed.word
            sung = word.timed and time >= word.start
            colour = text_style.colour_on if sung else text_style.colour_off
            if text_style.outline and text_style.outline_width > 0:
                draw.text(
                    (placed.x, placed.y),
                    placed.text,
                    font=cue.layout.font,
                    fill=_fade(text_style.outline, opacity),
                    stroke_width=text_style.outline_width,
                    stroke_fill=_fade(text_style.outline, opacity),
                )
            draw.text(
                (placed.x, placed.y),
                placed.text,
                font=cue.layout.font,
                fill=_fade(colour, opacity),
            )

        ball = self.style.ball
        position = ball_position(time, cue.layout, ball)
        if position is not None and ball.kind == "ball":
            radius = ball.radius
            draw.ellipse(
                (
                    position.x - radius,
                    position.y - radius,
                    position.x + radius,
                    position.y + radius,
                ),
                fill=_fade(ball.colour, opacity * position.opacity),
            )
        return image
