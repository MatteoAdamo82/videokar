"""Drawing the ball itself.

Pillow's ellipse has no anti-aliasing and rounds its coordinates to whole
pixels, which on a moving object shows: the outline is a fixed stair-step
pattern that jumps a pixel at a time, and at speed the eye reads the sliding
steps as the shape breathing. Measured on the reference track the disc was
exactly 33x33 in every frame while the position it was asked for moved in
fractions — all of the wobble was in the rasteriser.

So it is drawn into a small tile at several times the size and scaled back down,
which both smooths the edge and lets the fractional part of the position survive
into the picture.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw

SUPERSAMPLE = 4
"""Enough for a clean edge on a ball this size; more is invisible and slower."""


def _stretch(speed: float, squash: float, reference: float) -> tuple[float, float]:
    """How far to stretch along the travel, and squash across it.

    Area is preserved — the two factors are reciprocal — so the ball never looks
    like it is changing size, only shape.
    """
    if squash <= 0 or reference <= 0:
        return (1.0, 1.0)
    amount = 1.0 + squash * min(speed / reference, 1.0)
    return (amount, 1.0 / amount)


def draw_ball(
    image: Image.Image,
    x: float,
    y: float,
    radius: float,
    colour: tuple[int, int, int, int],
    *,
    squash: float = 0.0,
    dx: float = 0.0,
    dy: float = 0.0,
    reference_speed: float = 0.0,
) -> None:
    """Composite an anti-aliased ball centred on (x, y), stretched if asked."""
    speed = math.hypot(dx, dy)
    along, across = _stretch(speed, squash, reference_speed)

    # The tile has to hold the ball at its longest, whichever way it is pointing.
    reach = radius * max(along, 1.0)
    size = max(2, int(math.ceil(reach * 2)) + 3)
    scale = SUPERSAMPLE
    tile = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))

    # Fractional position is baked into where the ellipse sits inside the tile,
    # so the ball moves smoothly instead of snapping to whole pixels.
    left, top = math.floor(x - size / 2), math.floor(y - size / 2)
    # The half pixel is the difference between a coordinate and the centre of
    # the pixel it falls in; without it the ball sits consistently up and to the
    # left of where the geometry put it.
    cx = (x - left + 0.5) * scale
    cy = (y - top + 0.5) * scale
    rx, ry = radius * along * scale, radius * across * scale

    ImageDraw.Draw(tile).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=colour)

    if speed > 0 and (along, across) != (1.0, 1.0):
        # Point the long axis along the travel. Expand so the corners survive
        # the turn, then take the middle back.
        angle = math.degrees(math.atan2(-dy, dx))
        tile = tile.rotate(angle, resample=Image.BICUBIC, center=(cx, cy))

    image.alpha_composite(tile.resize((size, size), Image.LANCZOS), (left, top))
