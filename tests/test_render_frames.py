from dataclasses import replace

import pytest

from conftest import make_line, make_song
from videokar.config.schema import BallStyle, Layout, Output, Style, TextStyle, Timing
from videokar.render.frames import FrameRenderer

STYLE = Style(
    output=Output(width=400, height=200),
    layout=Layout(margin_x=0, margin_y=20, safe_area=0.0),
    timing=Timing(lead_in=0.8, hold=1.0, fade=0.3),
    main=TextStyle(size=20, outline=None),
    ball=BallStyle(radius=5),
)


def song(*lines):
    return make_song(*lines)


def two_lines():
    return song(make_line("l0", ["one", "two"], 10.0), make_line("l1", ["three"], 20.0))


def test_a_frame_is_the_requested_size_and_has_alpha():
    frame = FrameRenderer(two_lines(), STYLE).frame(10.5)
    assert frame.size == (400, 200)
    assert frame.mode == "RGBA"


def test_nothing_is_drawn_before_the_first_line():
    frame = FrameRenderer(two_lines(), STYLE).frame(0.0)
    assert frame.getbbox() is None


def test_the_right_line_is_on_screen():
    renderer = FrameRenderer(two_lines(), STYLE)
    assert renderer.cue_at(10.5).line.id == "l0"
    assert renderer.cue_at(20.5).line.id == "l1"


def test_a_line_appears_before_its_first_word_and_holds_after_its_last():
    renderer = FrameRenderer(two_lines(), STYLE)
    assert renderer.cue_at(9.5) is not None
    assert renderer.cue_at(11.5) is not None


def test_two_lines_are_never_on_screen_at_once():
    renderer = FrameRenderer(two_lines(), STYLE)
    for first, second in zip(renderer.cues, renderer.cues[1:], strict=False):
        assert first.leaves <= second.appears


def test_a_line_crowded_by_the_next_one_gives_way():
    # Lines a second apart: the hold on the first would otherwise run into the
    # lead-in of the second.
    renderer = FrameRenderer(
        song(make_line("l0", ["one"], 10.0), make_line("l1", ["two"], 11.0)), STYLE
    )
    assert renderer.cues[0].leaves <= renderer.cues[1].appears


def test_a_line_fades_in_and_out():
    renderer = FrameRenderer(two_lines(), STYLE)
    cue = renderer.cues[0]
    assert cue.opacity(cue.appears, 0.3) == pytest.approx(0.0, abs=0.01)
    assert cue.opacity(cue.appears + 0.3, 0.3) == pytest.approx(1.0, abs=0.01)
    assert cue.opacity(cue.leaves, 0.3) == pytest.approx(0.0, abs=0.01)


def test_a_hard_cut_has_no_fade():
    renderer = FrameRenderer(two_lines(), replace(STYLE, timing=Timing(fade=0.0)))
    cue = renderer.cues[0]
    assert cue.opacity(cue.appears, 0.0) == 1.0


def test_an_unsung_line_is_skipped():
    lines = song(
        make_line("l0", ["one"], 10.0, sung=False),
        make_line("l1", ["two"], 20.0),
    )
    assert [cue.line.id for cue in FrameRenderer(lines, STYLE).cues] == ["l1"]


def test_a_line_with_no_timings_is_skipped():
    line = make_line("l0", ["one"], 10.0)
    for word in line.words:
        word.start = word.end = None
    lines = song(line, make_line("l1", ["two"], 20.0))
    lines.refresh_bounds()
    assert [cue.line.id for cue in FrameRenderer(lines, STYLE).cues] == ["l1"]


def test_the_sung_part_of_a_line_is_drawn_differently():
    renderer = FrameRenderer(two_lines(), STYLE)
    before = renderer.frame(9.9)
    after = renderer.frame(10.2)
    assert before.tobytes() != after.tobytes()


def test_a_line_never_leaves_before_its_last_word_is_sung():
    # Lines follow each other closely in a real song: l0 ends at 20.607 and l1
    # starts at 20.65. Clamping the exit to next.start - lead_in put it at
    # 19.85, half a second before the last word was sung, so every line lost
    # its ending.
    lines = song(
        make_line("l0", ["one", "two", "three"], 18.0, step=0.87),
        make_line("l1", ["four", "five"], 20.65),
    )
    for cue in FrameRenderer(lines, STYLE).cues:
        assert cue.leaves >= cue.line.end


def test_the_last_word_of_a_line_is_still_drawn_when_it_is_sung():
    lines = song(
        make_line("l0", ["one", "two", "three"], 18.0, step=0.87),
        make_line("l1", ["four", "five"], 20.65),
    )
    renderer = FrameRenderer(lines, STYLE)
    last = lines.line("l0").words[-1]
    cue = renderer.cue_at((last.start + last.end) / 2)
    assert cue is not None and cue.line.id == "l0"


def test_a_line_is_visible_not_mid_fade_while_its_last_word_is_sung():
    lines = song(
        make_line("l0", ["one", "two", "three"], 18.0, step=0.87),
        make_line("l1", ["four", "five"], 20.65),
    )
    renderer = FrameRenderer(lines, STYLE)
    cue = renderer.cues[0]
    assert cue.opacity(cue.line.end, STYLE.timing.fade) == pytest.approx(1.0, abs=0.01)


def test_a_line_is_visible_while_its_first_word_is_sung():
    lines = song(make_line("l0", ["one", "two"], 10.0), make_line("l1", ["three"], 10.9))
    renderer = FrameRenderer(lines, STYLE)
    for cue in renderer.cues:
        assert cue.appears <= cue.line.start
        assert cue.opacity(cue.line.start, STYLE.timing.fade) == pytest.approx(1.0, abs=0.01)


@pytest.mark.parametrize(("width", "height"), [(320, 180), (960, 540), (1920, 1080)])
def test_the_ball_is_drawn_inside_the_frame_at_any_size(width, height):
    from videokar.config.schema import Output, Style, TextStyle

    lines = song(make_line("l0", ["one", "two", "three"], 10.0))
    style = Style(output=Output(width=width, height=height), main=TextStyle(outline=None))
    renderer = FrameRenderer(lines, style)
    cue = renderer.cues[0]
    from videokar.render.ball import ball_position

    # Sampled across the line: the arc must not leave the picture at any point.
    for step in range(20):
        position = ball_position(10.0 + step * 0.08, cue.layout, cue.ball)
        if position is None:
            continue
        assert 0 <= position.x <= width
        assert cue.ball.radius <= position.y <= height, f"{width}x{height} at step {step}"


def test_a_small_frame_still_fits_the_line_on_one_row():
    from videokar.config.schema import Output, Style, TextStyle

    words = ["She", "purrs", "she", "eats", "she", "stays", "a", "while"]
    lines = song(make_line("l0", words, 10.0))
    style = Style(output=Output(width=320, height=180), main=TextStyle(outline=None))
    assert FrameRenderer(lines, style).cues[0].layout.rows == 1


def test_no_shadow_unless_a_colour_is_given():
    from videokar.config.schema import Shadow

    assert Style().shadow.colour is None
    renderer = FrameRenderer(two_lines(), STYLE)
    assert renderer.cues[0].shadow is None
    assert FrameRenderer(two_lines(), replace(STYLE, shadow=Shadow())).cues[0].shadow is None


def test_a_shadow_is_drawn_behind_the_words():
    from videokar.config.schema import Shadow

    plain = FrameRenderer(two_lines(), STYLE).frame(10.5)
    shadowed = FrameRenderer(
        two_lines(), replace(STYLE, shadow=Shadow(colour=(0, 0, 0, 200)))
    ).frame(10.5)
    assert plain.tobytes() != shadowed.tobytes()
    # It covers more of the frame than the letters alone.
    assert shadowed.getbbox()[3] - shadowed.getbbox()[1] >= plain.getbbox()[3] - plain.getbbox()[1]


def test_the_shadow_is_drawn_once_per_line_not_once_per_frame():
    from videokar.config.schema import Shadow

    # Its shape does not change while a line is up — only the colour of the
    # words above it does — so blurring it per frame would be the same work
    # thousands of times over.
    renderer = FrameRenderer(two_lines(), replace(STYLE, shadow=Shadow(colour=(0, 0, 0, 200))))
    cue = renderer.cues[0]
    assert cue.shadow is not None
    assert renderer.cue_at(10.5).shadow is cue.shadow
    assert renderer.cue_at(11.2).shadow is cue.shadow


def test_the_shadow_fades_with_the_line():
    from videokar.config.schema import Shadow

    renderer = FrameRenderer(two_lines(), replace(STYLE, shadow=Shadow(colour=(0, 0, 0, 255))))
    cue = renderer.cues[0]
    entering = renderer.frame(cue.appears + 0.01)
    settled = renderer.frame(cue.line.start)
    assert entering.tobytes() != settled.tobytes()


def test_the_shadow_is_offset_from_the_text():
    from videokar.config.schema import Shadow, resolved_shadow

    offset_x, offset_y, blur = resolved_shadow(Shadow(), 64)
    assert offset_x > 0 and offset_y > 0 and blur > 0
    # And explicit values win, including a hard shadow.
    assert resolved_shadow(Shadow(offset_x=2, offset_y=-3, blur=0), 64) == (2, -3, 0)
