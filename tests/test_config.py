import pytest

from videokar.config import (
    ConfigError,
    Layout,
    Output,
    Style,
    TextStyle,
    available_presets,
    resolve_style,
    style_schema,
    to_dict,
    to_toml,
)


def write(tmp_path, text, name="videokar.toml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_no_config_at_all_is_the_defaults():
    assert resolve_style() == Style()


def test_every_preset_loads():
    assert available_presets()
    for name in available_presets():
        assert isinstance(resolve_style(preset=name), Style)


def test_an_unknown_preset_lists_the_real_ones():
    with pytest.raises(ConfigError, match="youtube"):
        resolve_style(preset="nope")


def test_a_file_overrides_a_preset(tmp_path):
    path = write(tmp_path, "[output]\nfps = 60\n")
    style = resolve_style(path, preset="youtube")
    assert style.output.fps == 60
    assert style.output.format == "mp4"  # still from the preset


def test_a_file_can_name_the_preset_it_builds_on(tmp_path):
    path = write(tmp_path, 'preset = "shorts"\n[output]\nfps = 24\n')
    style = resolve_style(path)
    assert style.output.height == 1920
    assert style.output.fps == 24


def test_merging_is_per_key_not_per_section(tmp_path):
    # Setting one colour must not reset the rest of the block around it.
    path = write(tmp_path, '[main]\ncolour_on = "#ff0000"\n')
    style = resolve_style(path)
    assert style.main.colour_on == (255, 0, 0, 255)
    assert style.main.outline_width == Style().main.outline_width


def test_overrides_win_over_the_file(tmp_path):
    path = write(tmp_path, "[output]\nfps = 60\n")
    assert resolve_style(path, overrides={"output": {"fps": 12}}).output.fps == 12


def test_a_missing_file_says_so(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        resolve_style(tmp_path / "nope.toml")


def test_broken_toml_says_so(tmp_path):
    with pytest.raises(ConfigError, match="not valid TOML"):
        resolve_style(write(tmp_path, "[output\nfps = 1"))


def test_a_bad_value_names_the_field_and_why(tmp_path):
    path = write(tmp_path, "[output]\nfps = 0\n")
    with pytest.raises(ConfigError) as caught:
        resolve_style(path)
    assert "output.fps" in str(caught.value)
    assert "greater than or equal to 1" in str(caught.value)


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("#ff0000", (255, 0, 0, 255)),
        ("#ff000080", (255, 0, 0, 128)),
        ("#f00", (255, 0, 0, 255)),
        ("ff0000", (255, 0, 0, 255)),
    ],
)
def test_colours_are_written_as_hex(tmp_path, written, expected):
    path = write(tmp_path, f'[main]\ncolour_on = "{written}"\n')
    assert resolve_style(path).main.colour_on == expected


def test_a_colour_that_is_not_one_says_so(tmp_path):
    with pytest.raises(ConfigError, match="not a colour"):
        resolve_style(write(tmp_path, '[main]\ncolour_on = "burnt sienna"\n'))


def test_colours_come_back_out_as_hex():
    assert to_dict(Style())["main"]["colour_on"] == "#ffeebeff"


def test_a_written_file_reads_back_the_same(tmp_path):
    for preset in [None, *available_presets()]:
        style = resolve_style(preset=preset)
        path = write(tmp_path, to_toml(style), name=f"{preset}.toml")
        assert resolve_style(path) == style


def test_an_unset_optional_section_stays_unset_through_a_round_trip(tmp_path):
    # An empty [paren] table is not "no second-voice style", it is a second
    # voice styled exactly like the first, so it has to stay commented out.
    path = write(tmp_path, to_toml(Style()))
    assert resolve_style(path).paren is None


def test_an_unset_size_stays_unset_through_a_round_trip(tmp_path):
    path = write(tmp_path, to_toml(Style()))
    assert resolve_style(path).main.size is None


def test_the_written_file_explains_itself():
    text = to_toml(Style())
    assert "# 'mp4' | 'prores4444' | 'png'" in text
    assert "makes a karaoke video look broken" in text


def test_the_schema_describes_every_section():
    schema = style_schema()
    assert set(schema["$defs"]) >= {"Output", "Layout", "Timing", "TextStyle", "BallStyle"}
    fps = schema["$defs"]["Output"]["properties"]["fps"]
    assert fps["maximum"] == 240
    # An editor needs the choices, not prose about them.
    assert schema["$defs"]["Output"]["properties"]["format"]["enum"] == [
        "mp4",
        "prores4444",
        "png",
    ]


def test_an_explicit_size_survives_but_the_default_follows_the_frame():
    assert Style(main=TextStyle(size=99)).resolved_size(TextStyle(size=99)) == 99
    tall = Style(output=Output(width=1080, height=1920))
    assert tall.resolved_size(tall.main) == 113


@pytest.mark.parametrize(("width", "height"), [(320, 180), (1280, 720), (1920, 1080), (3840, 2160)])
def test_the_geometry_follows_the_frame(width, height):
    from videokar.config.schema import resolved_ball, resolved_margins, resolved_size

    style = Style(output=Output(width=width, height=height))
    size = resolved_size(style.main, style.output)
    margin_x, margin_y = resolved_margins(style.layout, style.output)
    ball = resolved_ball(style.ball, size)

    # Margins have to leave most of the frame to write in. At 320x180 the fixed
    # 96px margin left 96px of usable width and wrapped every line into three.
    assert width - 2 * margin_x > width * 0.6
    assert margin_y < height * 0.2
    # And the ball has to fit above the text rather than fly off the top.
    assert ball.gap_above_text + ball.jump_height < height * 0.25
    assert 2 * ball.radius < size * 0.8


def test_the_ball_stays_in_frame_at_a_small_size():
    from videokar.config.schema import resolved_ball, resolved_margins, resolved_size
    from videokar.project import load_song  # noqa: F401

    style = Style(output=Output(width=320, height=180))
    size = resolved_size(style.main, style.output)
    _, margin_y = resolved_margins(style.layout, style.output)
    ball = resolved_ball(style.ball, size)
    text_top = 180 - round(180 * style.layout.safe_area) - margin_y - size * 1.15
    assert text_top - ball.gap_above_text - ball.jump_height - ball.radius > 0


def test_explicit_geometry_still_wins():
    from videokar.config.schema import BallStyle, resolved_ball, resolved_margins

    style = Style(
        output=Output(width=320, height=180),
        layout=Layout(margin_x=11, margin_y=13),
        ball=BallStyle(radius=7, jump_height=5.0, gap_above_text=3.0),
    )
    assert resolved_margins(style.layout, style.output) == (11, 13)
    ball = resolved_ball(style.ball, 12)
    assert (ball.radius, ball.jump_height, ball.gap_above_text) == (7, 5.0, 3.0)


def test_the_outline_scales_with_the_text():
    from videokar.config.schema import resolved_outline

    assert resolved_outline(TextStyle(), 64) == 3
    # A 3px outline on a 12px font is a blot, not an outline.
    assert resolved_outline(TextStyle(), 12) == 1
    assert resolved_outline(TextStyle(outline_width=9), 12) == 9


def test_a_default_render_at_1080p_is_unchanged():
    # The ratios were read off values tuned by eye there, so that frame must
    # come out exactly as it did before they became ratios.
    from videokar.config.schema import resolved_ball, resolved_margins, resolved_size

    style = Style()
    size = resolved_size(style.main, style.output)
    assert (size, resolved_margins(style.layout, style.output)) == (64, (96, 120))
    ball = resolved_ball(style.ball, size)
    assert (ball.radius, round(ball.jump_height), round(ball.gap_above_text)) == (16, 62, 26)
