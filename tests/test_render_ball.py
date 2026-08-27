import pytest

from conftest import make_line, make_song
from videokar.render.ball import ball_position
from videokar.render.layout import layout_line
from videokar.render.style import BallStyle, Layout, Output, TextStyle

OUTPUT = Output(width=1000, height=600)
LAYOUT = Layout(anchor="bottom", margin_x=0, margin_y=50, safe_area=0.0)
TEXT = TextStyle(size=40, outline=None)
BALL = BallStyle(lead_in=1.0, jump_height=60.0, gap_above_text=20.0, hide_after=2.0)


def lay(line):
    return layout_line(line, TEXT, LAYOUT, OUTPUT)


def three_words(start=10.0, step=1.0, gap=0.1):
    return make_song(make_line("l0", ["one", "two", "three"], start, step=step)).line("l0")


def test_nothing_is_drawn_before_the_run_in():
    layout = lay(three_words())
    assert ball_position(8.0, layout, BALL) is None


def test_the_run_in_arrives_on_the_first_word():
    layout = lay(three_words())
    arriving = ball_position(9.99, layout, BALL)
    first = layout.words[0]
    assert arriving is not None
    assert arriving.x == pytest.approx(first.centre_x, abs=1.0)


def test_the_run_in_starts_left_of_the_first_word():
    layout = lay(three_words())
    entering = ball_position(9.05, layout, BALL)
    assert entering.x < layout.words[0].centre_x


def test_the_ball_is_over_the_word_being_sung_when_it_starts():
    layout = lay(three_words())
    at_second = ball_position(11.0, layout, BALL)
    assert at_second.x == pytest.approx(layout.words[1].centre_x, abs=1.0)


def test_the_arc_peaks_between_two_words():
    layout = lay(three_words())
    start = ball_position(10.0, layout, BALL)
    middle = ball_position(10.5, layout, BALL)
    end = ball_position(11.0, layout, BALL)
    # Screen y grows downward, so higher up is a smaller number.
    assert middle.y < start.y
    assert middle.y < end.y
    assert middle.y == pytest.approx(start.y - BALL.jump_height, abs=1.0)


def test_the_ball_moves_forward_across_a_hop():
    layout = lay(three_words())
    xs = [ball_position(10.0 + i * 0.1, layout, BALL).x for i in range(11)]
    assert xs == sorted(xs)


def test_the_ball_rests_on_the_last_word():
    layout = lay(three_words())
    resting = ball_position(12.9, layout, BALL)
    assert resting.x == pytest.approx(layout.words[-1].centre_x, abs=1.0)


def with_gap(first_end, second_start):
    """Two words with real silence between them, not one very long word."""
    line = make_song(make_line("l0", ["one", "two"], 10.0)).line("l0")
    line.words[0].start, line.words[0].end = 10.0, first_end
    line.words[1].start, line.words[1].end = second_start, second_start + 0.4
    return line


def test_a_long_silence_inside_a_line_parks_then_hides_the_ball():
    layout = lay(with_gap(10.4, 18.0))
    # Sits on the word just sung...
    assert ball_position(10.4, layout, BALL) is not None
    # ...disappears rather than crawling across eight seconds of silence...
    assert ball_position(13.0, layout, BALL) is None
    # ...and runs in again before the next word.
    assert ball_position(17.6, layout, BALL) is not None


def test_a_short_gap_keeps_the_ball_travelling():
    # Half a second of rest is phrasing, not a break: the ball stays in flight.
    layout = lay(with_gap(10.4, 10.9))
    assert ball_position(10.6, layout, BALL) is not None


def test_no_ball_when_it_is_turned_off():
    layout = lay(three_words())
    assert ball_position(10.5, layout, BallStyle(kind="none")) is None


def test_no_ball_for_a_line_with_no_timings():
    line = make_song(make_line("l0", ["one", "two"], 10.0)).line("l0")
    for word in line.words:
        word.start = word.end = None
    assert ball_position(10.5, lay(line), BALL) is None
