from dataclasses import replace

import pytest

from conftest import make_line, make_song
from videokar.render.frames import FrameRenderer
from videokar.render.style import BallStyle, Layout, Output, Style, TextStyle, Timing

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
