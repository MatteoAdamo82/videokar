import pytest

from conftest import make_line, make_song
from videokar.render.layout import layout_line
from videokar.render.style import Layout, Output, Style, TextStyle

OUTPUT = Output(width=1000, height=600)
LAYOUT = Layout(anchor="bottom", margin_x=0, margin_y=50, safe_area=0.0)
STYLE = TextStyle(size=40, outline=None)


def lay(texts, style=STYLE, layout=LAYOUT, output=OUTPUT):
    song = make_song(make_line("l0", texts, 10.0))
    return layout_line(song.line("l0"), style, layout, output)


def test_every_word_is_placed_once_in_order():
    result = lay(["one", "two", "three"])
    assert [p.text for p in result.words] == ["one", "two", "three"]
    assert [p.x for p in result.words] == sorted(p.x for p in result.words)


def test_a_short_line_is_centred():
    result = lay(["one", "two"])
    left = min(p.x for p in result.words)
    right = max(p.x + p.width for p in result.words)
    assert (left + right) / 2 == pytest.approx(OUTPUT.width / 2, abs=1.0)


def test_a_short_line_is_one_row():
    assert lay(["one", "two", "three"]).rows == 1


def test_a_line_too_wide_shrinks_before_it_wraps():
    texts = ["antidisestablishmentarian", "supercalifragilistic"]
    big = lay(texts, style=TextStyle(size=60, min_scale=0.5, outline=None))
    assert big.rows == 1
    assert big.font.size < 60


def test_a_line_that_cannot_shrink_enough_wraps_instead():
    texts = ["antidisestablishmentarianism"] * 6
    # min_scale 0.95 leaves nowhere to shrink to, so it has to break.
    result = lay(texts, style=TextStyle(size=60, min_scale=0.95, outline=None))
    assert result.rows > 1
    assert len(result.words) == len(texts)


def test_wrapping_keeps_every_word_and_stacks_the_rows():
    result = lay(["antidisestablishmentarianism"] * 6, style=TextStyle(size=60, min_scale=0.95))
    rows = sorted({p.y for p in result.words})
    assert len(rows) == result.rows
    assert rows == sorted(rows)


def test_anchor_bottom_sits_lower_than_anchor_top():
    top = lay(["one"], layout=Layout(anchor="top", margin_y=50, safe_area=0.0))
    bottom = lay(["one"], layout=Layout(anchor="bottom", margin_y=50, safe_area=0.0))
    centre = lay(["one"], layout=Layout(anchor="center", margin_y=50, safe_area=0.0))
    assert top.words[0].y < centre.words[0].y < bottom.words[0].y


def test_the_safe_area_keeps_text_off_the_edges():
    wide = ["word"] * 12
    loose = lay(wide, layout=Layout(margin_x=0, safe_area=0.0))
    tight = lay(wide, layout=Layout(margin_x=0, safe_area=0.25))
    # A narrower usable width has to break the line into more rows.
    assert tight.rows > loose.rows


def test_the_second_voice_is_drawn_smaller_by_default():
    style = Style()
    assert style.voice_style("paren").size < style.voice_style("main").size


def test_an_explicit_second_voice_style_wins():
    style = Style(paren=TextStyle(size=99))
    assert style.voice_style("paren").size == 99
