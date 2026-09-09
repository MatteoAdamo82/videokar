"""The layer the words sit on."""

from __future__ import annotations

import pytest
from PIL import Image

from conftest import make_line, make_song
from videokar.config import resolve_style
from videokar.config.schema import Background
from videokar.render import FrameRenderer
from videokar.render.background import BackgroundError, base_frame, fit_image, forget_images


@pytest.fixture(autouse=True)
def _fresh_cache():
    forget_images()
    yield
    forget_images()


@pytest.fixture
def picture(tmp_path):
    """A wide picture: left half red, right half blue, so a crop is visible."""
    image = Image.new("RGB", (400, 100))
    image.paste((255, 0, 0), (0, 0, 200, 100))
    image.paste((0, 0, 255), (200, 0, 400, 100))
    path = tmp_path / "wall.png"
    image.save(path)
    return path


def test_cover_fills_the_frame_and_crops_the_overflow(picture):
    with Image.open(picture) as source:
        fitted = fit_image(source.convert("RGBA"), (100, 100), "cover")
    assert fitted.size == (100, 100)
    # 400x100 into a square: scaled to 400x400 and cropped to the middle, so the
    # seam between the halves lands in the centre and no edge is padding.
    assert fitted.getpixel((5, 50))[:3] == (255, 0, 0)
    assert fitted.getpixel((94, 50))[:3] == (0, 0, 255)


def test_contain_fits_the_whole_picture_and_pads(picture):
    with Image.open(picture) as source:
        fitted = fit_image(source.convert("RGBA"), (100, 100), "contain")
    assert fitted.size == (100, 100)
    # The strip is 4:1, so it sits as a band across the middle with black above.
    assert fitted.getpixel((50, 2))[:3] == (0, 0, 0)
    assert fitted.getpixel((5, 50))[:3] == (255, 0, 0)


def test_stretch_keeps_every_pixel_and_distorts(picture):
    with Image.open(picture) as source:
        fitted = fit_image(source.convert("RGBA"), (100, 100), "stretch")
    # No padding anywhere: both halves reach the top edge.
    assert fitted.getpixel((5, 2))[:3] == (255, 0, 0)
    assert fitted.getpixel((94, 2))[:3] == (0, 0, 255)


def test_dimming_darkens_without_greying(picture):
    bright = base_frame(Background(image=str(picture)), (100, 100), (0, 0, 0, 255))
    forget_images()
    dark = base_frame(Background(image=str(picture), dim=0.5), (100, 100), (0, 0, 0, 255))
    lit, dulled = bright.getpixel((5, 50)), dark.getpixel((5, 50))
    assert dulled[0] < lit[0]
    # Still red, not grey: the other channels have nothing to lose.
    assert dulled[1] == dulled[2] == 0
    assert dulled[3] == 255


def test_no_background_is_the_flat_fill():
    plain = base_frame(Background(), (8, 8), (12, 34, 56, 255))
    assert plain.getpixel((4, 4)) == (12, 34, 56, 255)


def test_a_frame_is_drawn_over_the_picture(picture):
    song = make_song(make_line("l0", ["ciao", "mondo"], 1.0))
    style = resolve_style(
        preset="youtube",
        overrides={"output": {"width": 200, "height": 120}, "background": {"image": str(picture)}},
    )
    frame = FrameRenderer(song, style).frame(1.2)
    assert frame.size == (200, 120)
    # The corner is picture, not the preset's flat background.
    assert frame.getpixel((3, 3))[:3] in {(255, 0, 0), (0, 0, 255)}


def test_a_background_on_a_transparent_export_is_refused(picture):
    song = make_song(make_line("l0", ["ciao"], 1.0))
    style = resolve_style(preset="alpha", overrides={"background": {"image": str(picture)}})
    with pytest.raises(BackgroundError, match="transparent overlay"):
        FrameRenderer(song, style)


def test_a_picture_that_is_not_one_says_so(tmp_path):
    broken = tmp_path / "not-a-picture.png"
    broken.write_text("hello")
    with pytest.raises(BackgroundError, match="could not be read"):
        base_frame(Background(image=str(broken)), (10, 10), (0, 0, 0, 255))


def test_an_image_and_a_video_together_are_refused():
    with pytest.raises(ValueError, match="not both"):
        Background(image="a.jpg", video="b.mp4")


def test_the_picture_is_read_once_for_a_whole_render(picture, monkeypatch):
    # Six thousand frames must not mean six thousand decodes.
    opens = []
    original = Image.open

    def counted(path, *args, **kwargs):
        opens.append(str(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Image, "open", counted)
    background = Background(image=str(picture))
    for _ in range(5):
        base_frame(background, (60, 40), (0, 0, 0, 255))
    assert opens.count(str(picture)) == 1


def test_each_frame_gets_its_own_copy(picture):
    background = Background(image=str(picture))
    first = base_frame(background, (60, 40), (0, 0, 0, 255))
    first.paste((0, 255, 0, 255), (0, 0, 60, 40))
    second = base_frame(background, (60, 40), (0, 0, 0, 255))
    # Drawing on one frame must not smear onto the next.
    assert second.getpixel((5, 20))[:3] != (0, 255, 0)
