import pytest

from conftest import make_line, make_song
from videokar.project.edit import (
    FixError,
    set_line_start,
    set_pinned,
    set_sung,
    set_word_start,
    shift_line,
    shift_word,
    stretch,
)


def four_lines():
    """l0 10-11.45, l1 20-21.45, l2 30-31.45, l3 40-41.45."""
    return make_song(
        make_line("l0", ["a", "b", "c"], 10.0),
        make_line("l1", ["d", "e", "f"], 20.0),
        make_line("l2", ["g", "h", "i"], 30.0),
        make_line("l3", ["j", "k", "l"], 40.0),
    )


def test_a_shift_moves_the_line():
    song = four_lines()
    shift_line(song, "l1", 2.0)
    assert song.line("l1").start == pytest.approx(22.0)


def test_a_shift_carries_the_lines_after_it():
    song = four_lines()
    shift_line(song, "l1", 2.0)
    assert song.line("l2").start == pytest.approx(32.0)
    assert song.line("l3").start == pytest.approx(42.0)


def test_a_shift_leaves_the_lines_before_it_alone():
    song = four_lines()
    shift_line(song, "l1", 2.0)
    assert song.line("l0").start == pytest.approx(10.0)


def test_a_pinned_line_stops_the_ripple():
    song = four_lines()
    set_pinned(song, "l3", True)
    shift_line(song, "l1", 2.0)
    # l3 is declared correct, so it does not move...
    assert song.line("l3").start == pytest.approx(40.0)
    # ...and l2 is redistributed into the span that is left.
    assert 22.0 < song.line("l2").start < 40.0


def test_the_redistributed_lines_start_after_the_shifted_one():
    # The bug this caught: the span was computed from the line's stale end, so
    # the following line was placed before the line that had just been moved.
    song = four_lines()
    set_pinned(song, "l3", True)
    shift_line(song, "l1", 8.0)
    assert song.line("l2").start > song.line("l1").end


def test_the_ripple_never_inverts_the_timeline():
    song = four_lines()
    set_pinned(song, "l3", True)
    shift_line(song, "l1", 8.0)
    starts = [ln.start for ln in song.lines if ln.start is not None]
    assert starts == sorted(starts)
    for first, second in zip(song.lines, song.lines[1:], strict=False):
        if first.end is not None and second.start is not None:
            assert first.end <= second.start


def test_a_shift_cannot_run_past_an_anchor():
    song = four_lines()
    set_pinned(song, "l2", True)
    with pytest.raises(FixError, match="past the anchor l2"):
        shift_line(song, "l1", 12.0)


def test_a_shift_that_squeezes_the_lines_between_to_nothing_says_so():
    song = four_lines()
    set_pinned(song, "l3", True)
    # Lands just short of the anchor, leaving l2 nowhere to go.
    with pytest.raises(FixError, match="no room"):
        shift_line(song, "l1", 18.54)


def test_a_shift_that_would_collide_backwards_is_refused():
    song = four_lines()
    with pytest.raises(FixError, match="before l0 ends"):
        shift_line(song, "l1", -10.0)


def test_a_pinned_line_cannot_be_shifted_by_accident():
    song = four_lines()
    set_pinned(song, "l1", True)
    with pytest.raises(FixError, match="pinned"):
        shift_line(song, "l1", 1.0)


def test_set_line_start_is_a_shift_to_an_absolute_time():
    song = four_lines()
    set_line_start(song, "l1", 25.0)
    assert song.line("l1").start == pytest.approx(25.0)
    assert song.line("l2").start == pytest.approx(35.0)


def test_moving_a_line_marks_its_words_edited():
    song = four_lines()
    shift_line(song, "l1", 2.0)
    assert all(w.manual for w in song.line("l1").words)


def test_moving_one_word_leaves_its_neighbours():
    song = four_lines()
    before = song.word("l1.w2").start
    shift_word(song, "l1.w1", 0.04)
    assert song.word("l1.w2").start == pytest.approx(before)


def test_a_word_cannot_be_pushed_past_its_neighbour():
    song = four_lines()
    with pytest.raises(FixError, match="after l1.w2 starts"):
        set_word_start(song, "l1.w1", 21.0)


def test_a_word_cannot_be_pulled_before_its_neighbour():
    song = four_lines()
    with pytest.raises(FixError, match="before l1.w0 ends"):
        set_word_start(song, "l1.w1", 20.0)


def test_stretch_fits_a_run_into_an_exact_span():
    song = four_lines()
    stretch(song, "l1", "l2", 22.0, 34.0)
    assert song.line("l1").start == pytest.approx(22.0)
    assert song.line("l2").end == pytest.approx(34.0)


def test_stretch_keeps_the_relative_spacing():
    # Proportional, not absolute: the gap keeps the same share of the run.
    song = four_lines()
    span = song.line("l2").end - song.line("l1").start
    before = (song.line("l2").start - song.line("l1").end) / span
    stretch(song, "l1", "l2", 20.0, 32.9)
    after = (song.line("l2").start - song.line("l1").end) / 12.9
    assert after == pytest.approx(before, rel=0.02)


def test_stretch_refuses_to_overlap_its_neighbours():
    song = four_lines()
    with pytest.raises(FixError, match="overlaps l3"):
        stretch(song, "l1", "l2", 22.0, 45.0)


def test_muting_a_line_drops_its_timing_but_keeps_its_words():
    song = four_lines()
    set_sung(song, "l1", False)
    line = song.line("l1")
    assert line.start is None
    assert line.words_text == "d e f"
    assert not line.sung


def test_unmuting_leaves_the_line_needing_a_realign():
    song = four_lines()
    set_sung(song, "l1", False)
    set_sung(song, "l1", True)
    assert song.line("l1").sung
    assert song.line("l1").start is None


def test_an_unknown_line_is_reported_clearly():
    with pytest.raises(FixError, match="l99"):
        shift_line(four_lines(), "l99", 1.0)


def test_retyping_a_line_keeps_the_timings_of_the_words_that_survive():
    from videokar.project.edit import set_line_text

    song = make_song(make_line("l0", ["Two", "person", "and", "gone"], 10.0))
    before = {w.text: (w.start, w.end) for w in song.line("l0").words}
    set_line_text(song, "l0", "Two purrs and gone")
    after = {w.text: (w.start, w.end) for w in song.line("l0").words}
    # Fixing one word costs nothing anywhere else.
    for word in ("Two", "and", "gone"):
        assert after[word] == before[word]


def test_a_word_added_by_retyping_is_fitted_between_its_neighbours():
    from videokar.project.edit import set_line_text

    song = make_song(make_line("l0", ["one", "three"], 10.0))
    set_line_text(song, "l0", "one two three")
    words = song.line("l0").words
    assert [w.text for w in words] == ["one", "two", "three"]
    assert words[0].end <= words[1].start
    assert words[1].end <= words[2].start


def test_retyping_can_shorten_a_line():
    from videokar.project.edit import set_line_text

    song = make_song(make_line("l0", ["one", "two", "three", "four"], 10.0))
    set_line_text(song, "l0", "one four")
    assert [w.text for w in song.line("l0").words] == ["one", "four"]
    assert song.line("l0").text == "one four"


def test_retyping_everything_spreads_the_words_over_the_old_span():
    from videokar.project.edit import set_line_text

    song = make_song(make_line("l0", ["aaa", "bbb"], 10.0))
    start, end = song.line("l0").start, song.line("l0").end
    set_line_text(song, "l0", "completely different words here")
    words = song.line("l0").words
    assert len(words) == 4
    assert words[0].start == pytest.approx(start, abs=0.01)
    assert words[-1].end == pytest.approx(end, abs=0.05)


def test_retyping_marks_the_line_as_touched_by_hand():
    from videokar.project.edit import set_line_text

    song = make_song(make_line("l0", ["one", "two"], 10.0))
    set_line_text(song, "l0", "one three")
    assert all(w.manual for w in song.line("l0").words)


def test_a_line_cannot_be_emptied_by_retyping():
    from videokar.project.edit import FixError, set_line_text

    song = make_song(make_line("l0", ["one", "two"], 10.0))
    with pytest.raises(FixError, match="mute it instead"):
        set_line_text(song, "l0", "   ")


def test_retyping_leaves_the_timeline_in_order():
    from videokar.project.edit import set_line_text

    song = four_lines()
    set_line_text(song, "l1", "d e f g h")
    timed = [w for w in song.words if w.timed]
    assert all(a.end <= b.start + 1e-6 for a, b in zip(timed, timed[1:], strict=False))


def test_a_word_appended_past_the_end_gets_a_real_duration():
    from videokar.project.edit import MIN_WORD, set_line_text

    # There is no room after the last word, so the line grows rather than the
    # new word coming out with start == end, which is not a word at all.
    song = make_song(make_line("l0", ["one", "two"], 10.0))
    end_before = song.line("l0").end
    set_line_text(song, "l0", "one two three")
    words = song.line("l0").words
    assert words[-1].end - words[-1].start >= MIN_WORD
    assert song.line("l0").end > end_before


def test_retyping_never_makes_a_word_of_no_length():
    from videokar.project.edit import set_line_text

    song = make_song(make_line("l0", ["one", "two"], 10.0))
    set_line_text(song, "l0", "one a b c d two e f")
    assert all(w.end > w.start for w in song.line("l0").words)


def test_retyping_leaves_check_with_nothing_to_report():
    from videokar.project import check_song
    from videokar.project.edit import set_line_text

    song = four_lines()
    set_line_text(song, "l1", "d e f g h i")
    assert check_song(song).errors == []



def test_a_line_grows_into_the_silence_but_not_into_the_next_line():
    from videokar.project.edit import set_line_text

    song = four_lines()
    limit = song.line("l2").start
    set_line_text(song, "l1", "d e f g h i j k l m n o p q r s t")
    assert song.line("l1").end <= limit
