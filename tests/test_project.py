import json

import pytest

from conftest import make_line, make_song
from videokar.project import SCHEMA_VERSION, ProjectError, check_song, load_song, save_song


def test_round_trip_through_disk(tmp_path):
    song = make_song(make_line("l0", ["one", "two", "three"], 10.0))
    path = save_song(song, tmp_path / "song.json")
    assert load_song(path) == song


def test_the_file_is_readable_and_uses_the_documented_key(tmp_path):
    song = make_song(make_line("l0", ["one"], 10.0))
    payload = json.loads(save_song(song, tmp_path / "song.json").read_text())
    assert payload["schema"] == SCHEMA_VERSION
    assert payload["sections"][0]["lines"][0]["words"][0]["text"] == "one"


def test_a_newer_schema_is_refused_rather_than_half_read(tmp_path):
    path = tmp_path / "song.json"
    path.write_text(json.dumps({"schema": SCHEMA_VERSION + 1}))
    with pytest.raises(ProjectError, match="upgrade"):
        load_song(path)


def test_broken_json_says_so(tmp_path):
    path = tmp_path / "song.json"
    path.write_text("{not json")
    with pytest.raises(ProjectError, match="not valid JSON"):
        load_song(path)


def test_bounds_come_from_the_words_underneath(tmp_path):
    song = make_song(make_line("l0", ["one", "two"], 10.0), make_line("l1", ["three"], 20.0))
    assert song.lines[0].start == 10.0
    assert song.lines[1].start == 20.0
    assert song.sections[0].start == 10.0
    assert song.sections[0].end == song.lines[1].end


def test_an_unsung_line_loses_its_timing():
    song = make_song(make_line("l0", ["one", "two"], 10.0, sung=False))
    assert song.lines[0].start is None


def test_lookup_by_id():
    song = make_song(make_line("l0", ["one", "two"], 10.0))
    assert song.line("l0").id == "l0"
    assert song.word("l0.w1").text == "two"
    assert song.section_of("l0").tag == "Verse 1"
    with pytest.raises(KeyError, match="l99"):
        song.line("l99")


def test_editing_a_word_makes_the_line_text_stale_but_breaks_nothing():
    song = make_song(make_line("l0", ["Two", "person"], 10.0))
    song.word("l0.w1").text = "purrs"
    line = song.line("l0")
    assert line.text_is_stale
    # The renderer draws the words, so it already shows the correction.
    assert line.words_text == "Two purrs"
    line.rebuild_text()
    assert not line.text_is_stale


def test_check_reports_a_stale_line_text():
    song = make_song(make_line("l0", ["Two", "person"], 10.0))
    song.word("l0.w1").text = "purrs"
    codes = [i.code for i in check_song(song).issues]
    assert "stale_line_text" in codes


def test_check_reports_a_stale_aligner_form():
    song = make_song(make_line("l0", ["Two", "person"], 10.0))
    song.word("l0.w1").text = "purrs"
    issue = next(i for i in check_song(song).issues if i.code == "stale_norm")
    assert "re-align" in issue.message


def test_check_reports_a_sung_line_with_no_timings():
    line = make_line("l0", ["one", "two"], 10.0)
    for w in line.words:
        w.start = w.end = None
    song = make_song(line)
    issue = next(i for i in check_song(song).issues if i.code == "untimed_line")
    assert issue.level == "error"


def test_check_reports_a_backwards_word():
    song = make_song(make_line("l0", ["one", "two"], 10.0))
    song.word("l0.w0").start, song.word("l0.w0").end = 12.0, 11.0
    assert any(i.code == "backwards_word" for i in check_song(song).issues)


def test_check_reports_lines_out_of_order():
    song = make_song(make_line("l0", ["one"], 20.0), make_line("l1", ["two"], 10.0))
    assert any(i.code == "out_of_order" for i in check_song(song).issues)


def test_check_writes_flags_back_when_asked():
    # Six words over twelve seconds is the smeared shape.
    song = make_song(make_line("l0", ["a", "b", "c", "d", "e", "f"], 10.0, step=2.0))
    assert song.lines[0].flags == []
    check_song(song, apply=True)
    assert "smeared" in song.lines[0].flags


def test_a_clean_song_reports_nothing():
    song = make_song(make_line("l0", ["one", "two", "three"], 10.0))
    report = check_song(song)
    assert report.ok
    assert report.issues == []
