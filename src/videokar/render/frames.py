"""One frame at a time.

Layouts are built once for the whole song and cached; a frame is a lookup, a
handful of text draws and a circle. That keeps the per-frame cost low enough
that the encoder, not the renderer, is the slow part.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from PIL import Image, ImageDraw

from ..config.schema import RGBA, Ball, Style, resolved_ball
from ..project.model import Line, Song
from .ball import ball_position
from .layout import LineLayout, layout_line
from .sprites import SpriteError, load_sprite


def _fade(colour: RGBA, opacity: float) -> RGBA:
    red, green, blue, alpha = colour
    return (red, green, blue, int(alpha * max(0.0, min(1.0, opacity))))


@dataclass(frozen=True, slots=True)
class Cue:
    """A line and the window it is on screen for.

    The window always contains the whole line: `appears` is at or before the
    first word and `leaves` is at or after the last. Fades are fitted into the
    room left over on either side rather than eating into the singing, so a word
    is never half faded while it is being sung.
    """

    line: Line
    layout: LineLayout
    appears: float
    leaves: float
    ball: Ball | None = None
    """The ball, with its dimensions settled against this line's text size."""

    fade_in: float = 0.0
    fade_out: float = 0.0

    def opacity(self, time: float, fade: float = 0.0) -> float:
        if self.fade_in > 0 and time < self.appears + self.fade_in:
            return max(0.0, (time - self.appears) / self.fade_in)
        if self.fade_out > 0 and time > self.leaves - self.fade_out:
            return max(0.0, (self.leaves - time) / self.fade_out)
        return 1.0


class FrameRenderer:
    """Draws the karaoke overlay for a song at any point in time."""

    def __init__(self, song: Song, style: Style | None = None) -> None:
        self.song = song
        self.style = style or Style()
        if self.style.ball.kind == "sprite":
            if not self.style.ball.sprite:
                raise SpriteError("the ball is set to 'sprite' but no image was given")
            # Fail here rather than on the first frame that wants it, which
            # would be minutes into a render.
            load_sprite(self.style.ball.sprite, 32)
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
        previous_leaves = float("-inf")
        for index, line in enumerate(sung):
            following = sung[index + 1] if index + 1 < len(sung) else None
            layout = layout_line(
                line,
                self.style.voice_style(line.voice),
                self.style.layout,
                self.style.output,
            )

            # Hand over to the next line somewhere between this line's last word
            # and its full hold — but never before that last word is sung. Lines
            # in a real song follow each other about forty milliseconds apart,
            # so clamping straight to `next.start - lead_in` cut the ending off
            # almost every line and dragged the whole song out of step.
            leaves = line.end + timing.hold
            if following is not None:
                handover = following.start - timing.lead_in
                leaves = min(leaves, max(handover, line.end + timing.fade))
                leaves = max(leaves, line.end)

            appears = min(line.start - timing.lead_in, line.start)
            appears = max(appears, previous_leaves)
            appears = min(appears, line.start)
            if leaves <= appears:
                leaves = appears + 1e-3

            cues.append(
                Cue(
                    line=line,
                    layout=layout,
                    appears=appears,
                    leaves=leaves,
                    ball=resolved_ball(self.style.ball, layout.size),
                    # Only fade in the room that is not being sung through.
                    fade_in=min(timing.fade, max(0.0, line.start - appears)),
                    fade_out=min(timing.fade, max(0.0, leaves - line.end)),
                )
            )
            previous_leaves = leaves
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
        opacity = cue.opacity(time)
        text_style = cue.layout.style

        for placed in cue.layout.words:
            word = placed.word
            sung = word.timed and time >= word.start
            colour = text_style.colour_on if sung else text_style.colour_off
            if text_style.outline and cue.layout.outline_width > 0:
                draw.text(
                    (placed.x, placed.y),
                    placed.text,
                    font=cue.layout.font,
                    fill=_fade(text_style.outline, opacity),
                    stroke_width=cue.layout.outline_width,
                    stroke_fill=_fade(text_style.outline, opacity),
                )
            draw.text(
                (placed.x, placed.y),
                placed.text,
                font=cue.layout.font,
                fill=_fade(colour, opacity),
            )

        ball = cue.ball
        position = ball_position(time, cue.layout, ball)
        if position is None:
            return image
        alpha = opacity * position.opacity

        if ball.kind == "sprite":
            sprite = load_sprite(ball.sprite, max(1, round(ball.radius * 2 * ball.sprite_scale)))
            if alpha < 1.0:
                faded = sprite.copy()
                faded.putalpha(faded.getchannel("A").point(lambda v: int(v * alpha)))
                sprite = faded
            # Centred on the same point the circle would have been drawn at, so
            # swapping one for the other does not move the bounce.
            image.alpha_composite(
                sprite,
                (round(position.x - sprite.width / 2), round(position.y - sprite.height / 2)),
            )
        elif ball.kind == "ball":
            radius = ball.radius
            draw.ellipse(
                (
                    position.x - radius,
                    position.y - radius,
                    position.x + radius,
                    position.y + radius,
                ),
                fill=_fade(ball.colour, alpha),
            )
        return image
