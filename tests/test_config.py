import pytest

from videokar.config import (
    ConfigError,
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
