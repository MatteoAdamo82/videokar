import pytest

from conftest import make_line, make_song
from videokar.config.schema import Layout, Output, Style, TextStyle
from videokar.render.layout import layout_line

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
    main = style.resolved_size(style.voice_style("main"))
    paren = style.resolved_size(style.voice_style("paren"))
    assert paren < main


def test_the_default_size_follows_the_frame_height():
    # One fixed size per render, but a preset should look the same at any
    # resolution without carrying a size for each.
    small = Style(output=Output(width=1280, height=720))
    large = Style(output=Output(width=3840, height=2160))
    assert small.resolved_size(small.main) == 42
    assert large.resolved_size(large.main) == 127


def test_an_explicit_size_is_left_alone():
    style = Style(output=Output(width=1280, height=720), main=TextStyle(size=99))
    assert style.resolved_size(style.main) == 99


def test_an_explicit_second_voice_size_wins():
    from videokar.config.schema import VoiceStyle

    style = Style(paren=VoiceStyle(size=99))
    assert style.voice_style("paren").size == 99


def test_a_margin_larger_than_the_frame_keeps_the_words_in_it():
    # A setting that silently renders an empty video is never what was meant.
    # 1500 is inside what the schema allows but far outside a 600px frame.
    result = lay(["one"], layout=Layout(anchor="bottom", margin_y=1500, safe_area=0.0))
    assert result.words[0].y >= 0
    assert result.words[0].y + result.words[0].height <= OUTPUT.height


def test_a_large_margin_still_moves_the_words_up():
    low = lay(["one"], layout=Layout(anchor="bottom", margin_y=50, safe_area=0.0))
    high = lay(["one"], layout=Layout(anchor="bottom", margin_y=400, safe_area=0.0))
    assert high.words[0].y < low.words[0].y


def test_the_words_can_be_placed_across_the_frame():
    # layout.x is the middle of the block, which is what a drag in the preview
    # writes back. Half is centred, which is where they always were.
    def middle(x):
        placed = lay(["ciao", "mondo"], layout=Layout(x=x, safe_area=0.0))
        left = min(word.x for word in placed.words)
        right = max(word.x + word.width for word in placed.words)
        return (left + right) / 2 / OUTPUT.width

    assert middle(0.5) == pytest.approx(0.5, abs=0.01)
    assert middle(0.25) < middle(0.5) < middle(0.75)


def test_the_words_are_held_inside_the_safe_area():
    # Dragged to an edge they stop at it rather than leaving the picture.
    for x in (0.0, 1.0):
        placed = lay(["una", "riga", "lunga"], layout=Layout(x=x, safe_area=0.05))
        assert min(word.x for word in placed.words) >= OUTPUT.width * 0.05 - 1
        assert max(word.x + word.width for word in placed.words) <= OUTPUT.width * 0.95 + 1


def test_an_exact_vertical_place_beats_the_anchor():
    # Two ways of saying where something goes; the more specific one answers.
    anchored = lay(["ciao"], layout=Layout(anchor="bottom", margin_y=20, safe_area=0.0))
    exact = lay(["ciao"], layout=Layout(anchor="bottom", margin_y=20, y=0.2, safe_area=0.0))
    assert min(w.y for w in anchored.words) > OUTPUT.height * 0.6
    assert min(w.y for w in exact.words) / OUTPUT.height == pytest.approx(0.2, abs=0.06)


def test_without_an_exact_place_the_anchor_still_decides():
    top = lay(["ciao"], layout=Layout(anchor="top", safe_area=0.0))
    bottom = lay(["ciao"], layout=Layout(anchor="bottom", safe_area=0.0))
    assert min(w.y for w in top.words) < min(w.y for w in bottom.words)
