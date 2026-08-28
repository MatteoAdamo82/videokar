import pytest
from PIL import Image

from conftest import make_line, make_song
from videokar.config.schema import BallStyle, Layout, Output, Style, TextStyle
from videokar.render.frames import FrameRenderer
from videokar.render.sprites import SpriteError, load_sprite

STYLE = Style(
    output=Output(width=400, height=200),
    layout=Layout(margin_x=0, margin_y=20, safe_area=0.0),
    main=TextStyle(size=20, outline=None),
)


@pytest.fixture
def sprite(tmp_path):
    """A wide blob with generous transparent margins around it."""
    image = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    for x in range(40, 160):
        for y in range(70, 130):
            image.putpixel((x, y), (255, 0, 0, 255))
    path = tmp_path / "blob.png"
    image.save(path)
    return path


def test_a_sprite_is_scaled_to_the_diameter_the_circle_would_have(sprite):
    loaded = load_sprite(str(sprite), 30)
    assert loaded.height == 30


def test_a_sprite_is_measured_on_what_is_drawn_not_on_its_canvas(sprite):
    # The blob is 120x60 inside a 200x200 file. Scaled to 30 high it must be
    # 60 wide, not 30 — otherwise a padded export silently comes out smaller.
    loaded = load_sprite(str(sprite), 30)
    assert loaded.size == (60, 30)


def test_a_sprite_keeps_its_transparency(sprite):
    loaded = load_sprite(str(sprite), 30)
    assert loaded.mode == "RGBA"
    assert loaded.getchannel("A").getextrema()[1] == 255


def test_a_missing_sprite_says_so(tmp_path):
    with pytest.raises(SpriteError, match="not found"):
        load_sprite(str(tmp_path / "nope.png"), 30)


def test_a_file_that_is_not_an_image_says_so(tmp_path):
    path = tmp_path / "notes.png"
    path.write_text("this is not a png")
    with pytest.raises(SpriteError, match="not an image"):
        load_sprite(str(path), 30)


def test_an_entirely_transparent_sprite_says_so(tmp_path):
    path = tmp_path / "empty.png"
    Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(path)
    with pytest.raises(SpriteError, match="entirely transparent"):
        load_sprite(str(path), 30)


def one_line():
    return make_song(make_line("l0", ["one", "two", "three"], 10.0))


def test_the_sprite_is_drawn(sprite):
    base = {f.name: getattr(STYLE, f.name) for f in STYLE.__dataclass_fields__.values()}
    style = Style(**{**base, "ball": BallStyle(kind="sprite", sprite=str(sprite))})
    frame = FrameRenderer(one_line(), style).frame(10.5)
    pixels = list(frame.convert("RGBA").getchannel("R").tobytes())
    reds = [value for value in pixels if value > 200]
    assert reds, "nothing of the sprite reached the frame"


def test_asking_for_a_sprite_without_one_fails_before_the_render(tmp_path):
    style = Style(output=Output(width=400, height=200), ball=BallStyle(kind="sprite"))
    with pytest.raises(SpriteError, match="no image was given"):
        FrameRenderer(one_line(), style)


def test_a_broken_sprite_fails_before_the_render_not_minutes_into_it(tmp_path):
    style = Style(
        output=Output(width=400, height=200),
        ball=BallStyle(kind="sprite", sprite=str(tmp_path / "nope.png")),
    )
    with pytest.raises(SpriteError, match="not found"):
        FrameRenderer(one_line(), style)


def test_the_sprite_lands_where_the_circle_would_have(sprite):
    from videokar.render.ball import ball_position

    base = {f.name: getattr(STYLE, f.name) for f in STYLE.__dataclass_fields__.values()}
    circle = FrameRenderer(one_line(), Style(**base))
    blob = FrameRenderer(
        one_line(), Style(**{**base, "ball": BallStyle(kind="sprite", sprite=str(sprite))})
    )
    at = 10.5
    a = ball_position(at, circle.cues[0].layout, circle.cues[0].ball)
    b = ball_position(at, blob.cues[0].layout, blob.cues[0].ball)
    # Swapping one for the other must not move the bounce.
    assert (a.x, a.y) == (b.x, b.y)
