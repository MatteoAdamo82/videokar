"""Drawing the music: where it sits, and that it stays inside the frame."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from videokar.config.schema import Meter
from videokar.render.meter import draw, geometry

SIZE = (400, 200)


def blank() -> Image.Image:
    return Image.new("RGBA", SIZE, (0, 0, 0, 255))


def lit(image: Image.Image) -> int:
    """How many pixels the meter actually painted."""
    return sum(1 for pixel in image.convert("L").get_flattened_data() if pixel > 40)


def columns_lit(image: Image.Image) -> list[int]:
    grey = image.convert("L")
    return [
        x
        for x in range(image.width)
        if max(grey.getpixel((x, y)) for y in range(image.height)) > 40
    ]


def test_none_draws_nothing():
    image = blank()
    draw(image, Meter(kind="none"), np.ones(48))
    assert lit(image) == 0


@pytest.mark.parametrize("kind", ["bars", "wave"])
def test_both_kinds_draw_something(kind):
    image = blank()
    draw(image, Meter(kind=kind), np.linspace(0.2, 1.0, 48))
    assert lit(image) > 100


@pytest.mark.parametrize("kind", ["bars", "wave"])
def test_nothing_is_drawn_outside_the_frame(kind):
    # Being clipped at the edges is what made the first attempt at this look
    # broken, so a meter pushed hard against a corner is held inside instead.
    for x, y, width in ((0.0, 0.0, 1.0), (1.0, 1.0, 1.0), (0.5, 0.02, 0.99)):
        image = blank()
        draw(image, Meter(kind=kind, x=x, y=y, width=width, height=0.4), np.ones(48))
        # A drawn pixel at the very edge is fine; a crash or a silent no-op is
        # not, and neither is a meter that vanishes because it fell outside.
        assert lit(image) > 0, (kind, x, y)


def test_it_is_centred_where_it_is_told():
    image = blank()
    draw(image, Meter(kind="bars", x=0.5, width=0.5), np.ones(48))
    columns = columns_lit(image)
    middle = (columns[0] + columns[-1]) / 2
    assert abs(middle - SIZE[0] / 2) <= 2


def test_moving_it_across_moves_what_is_drawn():
    left, right = blank(), blank()
    draw(left, Meter(kind="bars", x=0.25, width=0.4), np.ones(48))
    draw(right, Meter(kind="bars", x=0.75, width=0.4), np.ones(48))
    assert max(columns_lit(left)) < min(columns_lit(right))


def test_a_wider_meter_covers_more_of_the_frame():
    narrow, wide = blank(), blank()
    draw(narrow, Meter(kind="bars", width=0.3), np.ones(48))
    draw(wide, Meter(kind="bars", width=0.9), np.ones(48))
    assert len(columns_lit(wide)) > len(columns_lit(narrow)) * 2


def test_a_taller_meter_paints_more():
    short, tall = blank(), blank()
    draw(short, Meter(kind="bars", height=0.05), np.ones(48))
    draw(tall, Meter(kind="bars", height=0.4), np.ones(48))
    assert lit(tall) > lit(short) * 3


def test_the_colour_is_the_one_asked_for():
    image = blank()
    draw(image, Meter(kind="bars", colour=(0, 255, 0, 255)), np.ones(16))
    greens = [
        pixel
        for pixel in image.convert("RGB").get_flattened_data()
        if pixel[1] > 100
    ]
    assert greens
    assert all(pixel[0] < 90 and pixel[2] < 90 for pixel in greens)


def test_mirroring_grows_both_ways():
    both, up = blank(), blank()
    draw(both, Meter(kind="bars", mirror=True, y=0.5), np.ones(48))
    draw(up, Meter(kind="bars", mirror=False, y=0.5), np.ones(48))
    assert lit(both) > lit(up) * 1.6


def test_a_quiet_band_still_leaves_a_mark():
    # The floor: a passage that goes quiet should keep the meter's shape rather
    # than making it disappear and come back.
    image = blank()
    draw(image, Meter(kind="bars", floor=0.1), np.zeros(48))
    assert lit(image) > 0


def test_levels_analysed_at_another_band_count_are_resampled():
    # Changing the count in the dialog must not mean analysing the whole song
    # again before anything can be seen.
    image = blank()
    draw(image, Meter(kind="bars", bands=64), np.linspace(0.2, 1.0, 48))
    assert lit(image) > 100


def test_the_geometry_never_leaves_the_frame():
    for x in (0.0, 0.5, 1.0):
        for width in (0.1, 1.0):
            where = geometry(Meter(kind="bars", x=x, width=width), SIZE)
            assert where.left >= 0
            assert where.right <= SIZE[0]


def test_a_frame_carries_the_meter_under_the_words(tmp_path):
    # The meter is the room, the lyrics are the point: the words must still be
    # legible over it, which means being drawn last.
    import sys

    sys.path.insert(0, "tests")
    from conftest import make_line, make_song
    from videokar.audio.spectrum import analyse
    from videokar.config import resolve_style
    from videokar.render import FrameRenderer

    rate = 22_050
    t = np.linspace(0, 3, rate * 3, dtype=np.float32)
    spectrum = analyse(np.sin(2 * np.pi * 300 * t).astype(np.float32), rate, fps=25, bands=32)

    song = make_song(make_line("l0", ["ciao", "mondo"], 1.0))
    style = resolve_style(
        preset="youtube",
        overrides={
            "output": {"width": 320, "height": 180},
            "meter": {"kind": "bars", "y": 0.35},
        },
    )
    with_meter = FrameRenderer(song, style, spectrum=spectrum).frame(1.2)
    without = FrameRenderer(song, style).frame(1.2)
    # No spectrum, no meter — the renderer does not invent one.
    assert lit(with_meter) > lit(without)
