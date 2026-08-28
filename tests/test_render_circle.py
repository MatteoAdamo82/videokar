import numpy as np
import pytest
from PIL import Image

from videokar.render.circle import draw_ball

ORANGE = (255, 120, 70, 255)


def canvas():
    return Image.new("RGBA", (120, 120), (0, 0, 0, 255))


def measure(image):
    """Bounding box and weighted centre of the ball, on a black ground."""
    pixels = np.array(image.convert("RGB")).astype(float)
    weight = pixels[:, :, 0] - pixels[:, :, 2]
    mask = weight > 30
    ys, xs = np.nonzero(mask)
    values = weight[mask]
    return {
        "width": xs.max() - xs.min() + 1,
        "height": ys.max() - ys.min() + 1,
        "x": (xs * values).sum() / values.sum(),
        "y": (ys * values).sum() / values.sum(),
        "area": float(values.sum()),
    }


def test_the_edge_is_smooth_not_a_staircase():
    image = canvas()
    draw_ball(image, 60, 60, 16, ORANGE)
    reds = np.array(image.convert("RGB"))[:, :, 0]
    # Pillow's own ellipse gives exactly two values here: ground and fill.
    assert len(np.unique(reds)) > 20


def test_the_ball_lands_where_it_was_asked_to():
    image = canvas()
    draw_ball(image, 60.5, 59.25, 16, ORANGE)
    found = measure(image)
    assert found["x"] == pytest.approx(60.5, abs=0.25)
    assert found["y"] == pytest.approx(59.25, abs=0.25)


def test_half_a_pixel_of_movement_reaches_the_picture():
    # The old rasteriser rounded to whole pixels, so a ball crossing a frame
    # smoothly jumped, and the sliding stair-steps read as the shape wobbling.
    first, second = canvas(), canvas()
    draw_ball(first, 60.0, 60.0, 16, ORANGE)
    draw_ball(second, 60.5, 60.0, 16, ORANGE)
    assert first.tobytes() != second.tobytes()
    assert measure(second)["x"] - measure(first)["x"] == pytest.approx(0.5, abs=0.15)


def test_the_ball_keeps_its_size_as_it_moves():
    sizes = set()
    for step in range(8):
        image = canvas()
        draw_ball(image, 50 + step * 0.37, 60, 16, ORANGE)
        found = measure(image)
        sizes.add((found["width"], found["height"]))
    assert len(sizes) <= 2, f"the disc changed shape while moving: {sizes}"


def test_without_squash_it_stays_round():
    image = canvas()
    draw_ball(image, 60, 60, 16, ORANGE, squash=0.0, dx=100, dy=0, reference_speed=100)
    found = measure(image)
    assert found["width"] == found["height"]


def test_squash_stretches_along_the_travel():
    image = canvas()
    draw_ball(image, 60, 60, 16, ORANGE, squash=0.4, dx=100, dy=0, reference_speed=100)
    found = measure(image)
    assert found["width"] > found["height"]


def test_squash_follows_the_direction_rather_than_an_axis():
    sideways, downward = canvas(), canvas()
    draw_ball(sideways, 60, 60, 16, ORANGE, squash=0.4, dx=100, dy=0, reference_speed=100)
    draw_ball(downward, 60, 60, 16, ORANGE, squash=0.4, dx=0, dy=100, reference_speed=100)
    assert measure(sideways)["width"] > measure(sideways)["height"]
    assert measure(downward)["height"] > measure(downward)["width"]


def test_squash_keeps_the_area_so_it_does_not_look_to_change_size():
    round_ball, stretched = canvas(), canvas()
    draw_ball(round_ball, 60, 60, 16, ORANGE)
    draw_ball(stretched, 60, 60, 16, ORANGE, squash=0.4, dx=100, dy=0, reference_speed=100)
    assert measure(stretched)["area"] == pytest.approx(measure(round_ball)["area"], rel=0.12)


def test_a_stationary_ball_is_not_stretched():
    image = canvas()
    draw_ball(image, 60, 60, 16, ORANGE, squash=0.6, dx=0, dy=0, reference_speed=100)
    found = measure(image)
    assert found["width"] == found["height"]
