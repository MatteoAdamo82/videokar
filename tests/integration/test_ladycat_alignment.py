"""End-to-end alignment against the real track.

Slow — separation is cached after the first run, but the acoustic model still
has to look at three minutes of audio. Skipped automatically when the audio or
the ML extras are missing:

    uv run pytest -m integration
    uv run pytest -m "not integration"    # everything else
"""

from __future__ import annotations

import pytest

from videokar.lyrics import parse_lyrics_file

pytestmark = pytest.mark.integration

torch = pytest.importorskip("torch", reason="needs the align extra")


@pytest.fixture(scope="module")
def aligned(ladycat_audio_path, ladycat_lyrics_path):
    from videokar.pipeline import run_alignment

    return run_alignment(ladycat_audio_path, parse_lyrics_file(ladycat_lyrics_path))


def test_every_word_gets_a_timing(aligned):
    assert len(aligned.alignment.words) == len(aligned.lyrics.alignable_words)
    assert [w.word for w in aligned.alignment.words] == aligned.lyrics.alignable_words


def test_timings_are_monotonically_increasing(aligned):
    words = aligned.alignment.words
    assert all(w.start < w.end for w in words)
    assert all(a.end <= b.start + 1e-6 for a, b in zip(words, words[1:], strict=False))


def test_timings_stay_inside_the_track(aligned):
    duration = aligned.audio.duration
    assert aligned.alignment.words[0].start >= 0.0
    assert aligned.alignment.words[-1].end <= duration


def test_the_vocal_stem_was_used(aligned):
    assert aligned.separation is not None
    assert aligned.separation.vocals_path.exists()


def test_vocal_regions_look_like_a_song_not_a_smear(aligned):
    from videokar.audio.vad import total_voiced

    regions = aligned.regions
    assert len(regions) > 1, "a whole track as one region means the VAD found nothing"
    voiced = total_voiced(regions)
    # Roughly half a pop song is singing; well outside this and something broke.
    assert 0.15 < voiced / aligned.audio.duration < 0.90


def test_most_words_land_where_someone_is_singing(aligned):
    from videokar.audio.vad import in_any_region

    words = aligned.alignment.words
    inside = sum(in_any_region(w.start, aligned.regions, tolerance=0.25) for w in words)
    # The star token should keep the aligner out of the instrumental sections.
    assert inside / len(words) > 0.90


def test_the_first_line_starts_after_the_intro(aligned):
    # The prototype's notes put the first vocal at ~16.5s; anything at zero
    # means the aligner front-loaded the whole lyric.
    assert aligned.alignment.words[0].start > 5.0


def test_the_known_bad_chorus_is_flagged_not_silently_wrong(aligned):
    from videokar.align.confidence import analyse

    reports = analyse(
        aligned.alignment.words, group_count=len(aligned.lyrics), regions=aligned.regions
    )
    # Whisper puts four chorus phrases in 56-72s where lyrics.txt has three, so
    # the aligner has nowhere good to put them and stretches one line across the
    # difference. The point of the confidence pass is that this surfaces.
    around_chorus = [r for r in reports if 45.0 <= r.start <= 75.0]
    assert any(r.suspicious for r in around_chorus), "the tool must not report this as clean"


def test_most_of_the_song_is_not_flagged(aligned):
    from videokar.align.confidence import analyse

    reports = analyse(
        aligned.alignment.words, group_count=len(aligned.lyrics), regions=aligned.regions
    )
    # A checker that flags everything is as useless as one that flags nothing.
    assert sum(r.suspicious for r in reports) / len(reports) < 0.35


def test_the_pivot_document_round_trips(aligned, tmp_path):
    from videokar.project import build_song, check_song, load_song, save_song

    song = build_song(aligned)
    path = save_song(song, tmp_path / "ladycat.json")
    reloaded = load_song(path)

    assert reloaded == song
    assert len(reloaded.words) == sum(len(line.tokens) for line in aligned.lyrics.lines)
    assert len(reloaded.lines) == len(aligned.lyrics)
    # Empty sections survive: [Soft Intro], [Instrumental], [Fade-Outro].
    assert [s.tag for s in reloaded.sections if not s.lines] == [
        "Soft Intro",
        "Instrumental",
        "Fade-Outro",
    ]
    # Nothing hand-edited yet, so the only findings are alignment shape.
    assert check_song(reloaded).errors == []


def test_word_timings_in_the_document_are_monotonic(aligned):
    from videokar.project import build_song

    timed = [w for w in build_song(aligned).words if w.timed]
    assert all(a.end <= b.start + 1e-6 for a, b in zip(timed, timed[1:], strict=False))


def test_a_word_the_aligner_never_saw_keeps_its_place_without_timing(aligned):
    from videokar.project import build_song

    song = build_song(aligned)
    for line in song.lines:
        # One drawable token per written word, timed or not.
        assert len(line.words) == len(line.words_text.split())


def test_the_whole_song_renders_to_a_file_with_alpha(aligned, tmp_path):
    from dataclasses import replace

    from videokar.project import build_song
    from videokar.render import FrameRenderer, Output, Style, TextStyle
    from videokar.render.encode import have_ffmpeg, render_segmented

    if not have_ffmpeg():
        pytest.skip("ffmpeg is not on PATH")

    song = build_song(aligned)
    # Small and coarse: this checks the pipe and the file, not the picture.
    style = Style(
        output=Output(width=320, height=180, fps=6, segment_seconds=30.0),
        main=TextStyle(size=14),
    )
    renderer = FrameRenderer(song, style)
    assert len(renderer.cues) == len([ln for ln in song.lines if ln.start is not None])

    destination = tmp_path / "ladycat.mov"
    render_segmented(
        renderer.frame, destination, style.output, start=0.0, end=20.0, audio_path=None
    )
    assert destination.stat().st_size > 0

    # A frame during the first line has something on it; the intro does not.
    assert renderer.frame(2.0).getbbox() is None
    assert renderer.frame(song.lines[0].start + 0.1).getbbox() is not None

    muted = replace(style, output=replace(style.output, format="mp4", background=(0, 0, 0, 255)))
    assert FrameRenderer(song, muted).frame(song.lines[0].start).mode == "RGBA"
