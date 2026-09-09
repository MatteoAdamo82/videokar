"""The music, drawn.

Drawn here, in Pillow, rather than by one of ffmpeg's own filters. The filters
draw whatever they draw: their size, their placement and their colours are not
really ours to choose, which is how an earlier attempt ended up off-centre and
clipped at the edges. A few rectangles are not much code, and every pixel of
them is decided in this file.

Everything is laid out from fractions of the frame, so the same settings hold
at 1080p and in a vertical short, and the geometry is worked out once per
render rather than once per frame.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

from ..config.schema import Meter

SUPERSAMPLE = 4
"""Drawn this much larger and scaled down. A bar is a rectangle whose width is
rarely a whole number of pixels, and a hard edge on a sub-pixel boundary is what
makes a meter look like a picket fence rather than a graphic."""


@dataclass(frozen=True)
class Geometry:
    """Where the bars go, in pixels, worked out once."""

    left: int
    centre_y: int
    width: int
    reach: int
    """How far a full-scale band travels from the baseline."""
    pitch: float
    bar: float

    @property
    def right(self) -> int:
        return self.left + self.width


def geometry(meter: Meter, size: tuple[int, int]) -> Geometry:
    """Fractions of the frame, settled into pixels.

    Held inside the frame rather than allowed to run off it: a meter wider than
    the picture, or centred close enough to an edge to hang over it, is the
    thing that made the old one look broken.
    """
    frame_w, frame_h = size
    width = max(4, round(frame_w * meter.width))
    left = round(frame_w * meter.x - width / 2)
    left = max(0, min(left, frame_w - width))
    centre_y = max(0, min(round(frame_h * meter.y), frame_h))
    reach = max(1, round(frame_h * meter.height))
    pitch = width / max(1, meter.bands)
    return Geometry(
        left=left,
        centre_y=centre_y,
        width=width,
        reach=reach,
        pitch=pitch,
        bar=max(1.0, pitch * (1.0 - meter.gap)),
    )


def _heights(levels: np.ndarray, meter: Meter, reach: int) -> np.ndarray:
    """Band levels as pixel heights, never quite zero."""
    if levels.size != meter.bands:
        # Analysed at one band count and drawn at another: resample rather than
        # refuse, so changing the count in the dialog does not mean analysing
        # the whole song again before anything can be seen.
        source = np.linspace(0.0, 1.0, levels.size)
        target = np.linspace(0.0, 1.0, meter.bands)
        levels = np.interp(target, source, levels)
    scaled = np.clip(levels, 0.0, 1.0) * (1.0 - meter.floor) + meter.floor
    return scaled * reach


def draw(
    image: Image.Image, meter: Meter, levels: np.ndarray, *, alpha: float = 1.0
) -> None:
    """Paint the meter onto a frame, in place."""
    if meter.kind == "none" or alpha <= 0.0:
        return
    where = geometry(meter, image.size)
    heights = _heights(np.asarray(levels, dtype=np.float32), meter, where.reach)

    red, green, blue, opacity = meter.colour
    colour = (red, green, blue, max(0, min(255, round(opacity * alpha))))

    # Drawn into its own layer at several times the size and scaled back down:
    # the alternative is rectangles snapped to whole pixels, which at these
    # widths is visibly uneven from bar to bar.
    span_down = where.reach if meter.mirror else 0
    top = max(0, where.centre_y - where.reach)
    bottom = min(image.height, where.centre_y + span_down + 1)
    if bottom <= top:
        return

    box = (where.left, top, where.right, bottom)
    tile = Image.new(
        "RGBA", ((box[2] - box[0]) * SUPERSAMPLE, (box[3] - box[1]) * SUPERSAMPLE), (0, 0, 0, 0)
    )
    pen = ImageDraw.Draw(tile)
    middle = (where.centre_y - top) * SUPERSAMPLE

    if meter.kind == "wave":
        _wave(pen, meter, heights, where, middle, colour)
    else:
        _bars(pen, meter, heights, where, middle, colour)

    tile = tile.resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
    image.alpha_composite(tile, (box[0], box[1]))


def _bars(pen, meter: Meter, heights: np.ndarray, where: Geometry, middle: float, colour) -> None:
    if meter.baseline:
        # A dashed rule, so silence still reads as a meter rather than as
        # nothing at all — and so the bars are seen to stand on something.
        thickness = max(1, round(SUPERSAMPLE * 0.75))
        dash = where.pitch * SUPERSAMPLE
        for band in range(meter.bands):
            start = band * dash
            pen.rectangle(
                [start, middle - thickness / 2, start + dash * 0.55, middle + thickness / 2],
                fill=colour,
            )

    for band, height in enumerate(heights):
        centre = (band + 0.5) * where.pitch * SUPERSAMPLE
        half = where.bar * SUPERSAMPLE / 2
        rise = height * SUPERSAMPLE
        pen.rectangle(
            [centre - half, middle - rise, centre + half, middle + (rise if meter.mirror else 0)],
            fill=colour,
        )


def _wave(pen, meter: Meter, heights: np.ndarray, where: Geometry, middle: float, colour) -> None:
    """One filled shape following the band tops, rather than a bar each.

    The outline is resampled to four points per band and run through a small
    moving average, because a polygon straight through the band tops is a row
    of spikes — recognisably the same data, but not a wave.
    """
    span = where.width * SUPERSAMPLE
    detail = max(8, meter.bands * 4)
    across = np.linspace(0.0, span, detail)
    tops = np.interp(
        np.linspace(0.0, 1.0, detail),
        np.linspace(0.0, 1.0, heights.size),
        heights,
    ) * SUPERSAMPLE
    window = max(3, detail // meter.bands * 2 + 1)
    kernel = np.ones(window) / window
    tops = np.convolve(np.pad(tops, window // 2, mode="edge"), kernel, mode="valid")[:detail]

    upper = [(x, middle - y) for x, y in zip(across, tops, strict=True)]
    if meter.mirror:
        lower = [(x, middle + y) for x, y in zip(across, tops, strict=True)]
    else:
        lower = [(x, middle) for x in across]
    pen.polygon(upper + list(reversed(lower)), fill=colour)
