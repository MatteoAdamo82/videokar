import pytest

from videokar.align.base import WordTiming
from videokar.align.confidence import Flag, analyse, group_words
from videokar.audio.vad import Region


def line(group, times, *, score=0.2, first_index=0):
    return [
        WordTiming(first_index + i, group, f"w{i}", start, end, score)
        for i, (start, end) in enumerate(times)
    ]


def evenly(group, start, end, count, **kwargs):
    step = (end - start) / count
    times = [(start + i * step, start + (i + 1) * step - 0.01) for i in range(count)]
    return line(group, times, **kwargs)


def test_a_normal_line_is_not_flagged():
    words = evenly(0, 10.0, 13.0, 6) + evenly(1, 14.0, 17.0, 6)
    reports = analyse(words, group_count=2)
    assert reports[0].flags == []
    assert reports[0].rate == pytest.approx(2.0, abs=0.1)


def test_a_line_smeared_across_a_gap_is_flagged():
    # Six words over twelve seconds: the instrumental-break failure.
    words = evenly(0, 10.0, 22.0, 6) + evenly(1, 23.0, 26.0, 6)
    assert Flag.SMEARED in analyse(words, group_count=2)[0].flags


def test_a_crammed_line_is_flagged():
    words = evenly(0, 10.0, 13.0, 6) + evenly(1, 13.5, 14.4, 8)
    assert Flag.CRAMMED in analyse(words, group_count=2)[1].flags


def test_a_very_short_line_is_not_judged_on_its_rate():
    # Two words in a third of a second is a fast rate but nothing to act on.
    words = line(0, [(10.0, 10.1), (10.2, 10.3)]) + evenly(1, 12.0, 15.0, 6)
    assert Flag.CRAMMED not in analyse(words, group_count=2)[0].flags


def test_a_long_silence_inside_a_line_is_flagged():
    words = line(0, [(10.0, 10.4), (10.5, 10.9), (14.0, 14.4), (14.5, 14.9)])
    assert Flag.INTERNAL_GAP in analyse(words, group_count=1)[0].flags


def test_a_line_placed_where_nobody_sings_is_flagged():
    words = evenly(0, 10.0, 13.0, 6) + evenly(1, 40.0, 43.0, 6)
    reports = analyse(words, group_count=2, regions=[Region(9.0, 14.0)])
    assert reports[0].flags == []
    assert Flag.OUTSIDE_VOCAL in reports[1].flags


def test_overlap_with_the_following_line_is_flagged():
    words = evenly(0, 10.0, 16.0, 6) + evenly(1, 14.0, 20.0, 6)
    assert Flag.OVERLAPS_NEXT in analyse(words, group_count=2)[0].flags


def test_low_score_is_relative_to_the_track_not_absolute():
    # Every line is well under 0.5: on sung audio that is normal, and an
    # absolute threshold would flag the entire song.
    words = (
        evenly(0, 10.0, 13.0, 6, score=0.20)
        + evenly(1, 14.0, 17.0, 6, score=0.22)
        + evenly(2, 18.0, 21.0, 6, score=0.19)
    )
    assert all(r.flags == [] for r in analyse(words, group_count=3))

    words = (
        evenly(0, 10.0, 13.0, 6, score=0.20)
        + evenly(1, 14.0, 17.0, 6, score=0.22)
        + evenly(2, 18.0, 21.0, 6, score=0.01)
    )
    reports = analyse(words, group_count=3)
    assert reports[2].flags == [Flag.LOW_SCORE]
    assert reports[0].flags == []


def test_empty_groups_survive_the_round_trip():
    words = evenly(0, 10.0, 13.0, 3) + evenly(2, 14.0, 17.0, 3)
    grouped = group_words(words, 3)
    assert [len(g) for g in grouped] == [3, 0, 3]
    # A line with nothing alignable produces no report but does not shift the
    # indices of the lines after it.
    assert [r.index for r in analyse(words, group_count=3)] == [0, 2]


def test_a_line_declared_correct_keeps_its_score_but_loses_the_flag():
    words = (
        evenly(0, 10.0, 13.0, 6, score=0.20)
        + evenly(1, 14.0, 17.0, 6, score=0.22)
        + evenly(2, 18.0, 21.0, 6, score=0.01)
    )
    noisy = analyse(words, group_count=3)
    assert Flag.LOW_SCORE in noisy[2].flags

    settled = analyse(words, group_count=3, adjudicated=[2])
    assert settled[2].flags == []
    assert settled[2].score == pytest.approx(0.01)


def test_adjudicating_a_line_does_not_hide_a_real_problem():
    # A low score is an opinion a person can overrule. A line smeared across
    # twelve seconds is the shape of what is in the file, and still is.
    words = evenly(0, 10.0, 22.0, 6, score=0.01) + evenly(1, 23.0, 26.0, 6, score=0.2)
    flags = analyse(words, group_count=2, adjudicated=[0])[0].flags
    assert Flag.LOW_SCORE not in flags
    assert Flag.SMEARED in flags


def test_adjudicating_one_line_leaves_the_others_flagged():
    # Two outliers against a normal-looking track: adjudicating one must not
    # quieten the other. (Make most of the track low and it stops being an
    # outlier — that is the relative threshold working, not a bug.)
    words = (
        evenly(0, 10.0, 13.0, 6, score=0.20)
        + evenly(1, 14.0, 17.0, 6, score=0.22)
        + evenly(2, 18.0, 21.0, 6, score=0.19)
        + evenly(3, 22.0, 25.0, 6, score=0.005)
        + evenly(4, 26.0, 29.0, 6, score=0.005)
    )
    reports = analyse(words, group_count=5, adjudicated=[3])
    assert reports[3].flags == []
    assert Flag.LOW_SCORE in reports[4].flags
