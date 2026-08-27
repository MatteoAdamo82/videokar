import json

from typer.testing import CliRunner

from conftest import make_line, make_song
from videokar import __version__
from videokar.cli import app
from videokar.project import load_song, save_song

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_lyrics_table(ladycat_lyrics_path):
    result = runner.invoke(app, ["lyrics", str(ladycat_lyrics_path)])
    assert result.exit_code == 0
    assert "Verse 1" in result.stdout
    assert "36" in result.stdout


def test_lyrics_json(ladycat_lyrics_path):
    result = runner.invoke(app, ["lyrics", str(ladycat_lyrics_path), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    tags = [s["tag"] for s in payload["sections"]]
    assert tags[:2] == ["Soft Intro", "Verse 1"]


def test_missing_file_exits_nonzero(tmp_path):
    result = runner.invoke(app, ["lyrics", str(tmp_path / "nope.txt")])
    assert result.exit_code == 1


def _song_file(tmp_path, **kwargs):
    song = make_song(make_line("l0", ["one", "two", "three"], 10.0, **kwargs))
    return save_song(song, tmp_path / "song.json")


def test_check_on_a_clean_song(tmp_path):
    result = runner.invoke(app, ["check", str(_song_file(tmp_path))])
    assert result.exit_code == 0
    assert "0 suspicious" in result.stdout
    assert "0 errors" in result.stdout


def test_check_shows_every_line_with_all(tmp_path):
    result = runner.invoke(app, ["check", str(_song_file(tmp_path)), "--all"])
    assert result.exit_code == 0
    assert "l0" in result.stdout


def test_check_exits_nonzero_on_an_error(tmp_path):
    path = _song_file(tmp_path)
    song = load_song(path)
    song.word("l0.w0").start, song.word("l0.w0").end = 12.0, 11.0
    save_song(song, path)
    result = runner.invoke(app, ["check", str(path)])
    assert result.exit_code == 1
    assert "backwards" in result.stdout or "ends at" in result.stdout


def test_check_write_persists_the_flags(tmp_path):
    song = make_song(make_line("l0", list("abcdef"), 10.0, step=2.0))
    path = save_song(song, tmp_path / "song.json")
    runner.invoke(app, ["check", str(path), "--write"])
    assert "smeared" in load_song(path).line("l0").flags


def test_punctuation_added_by_hand_does_not_count_as_a_stale_aligner_form(tmp_path):
    path = _song_file(tmp_path)
    song = load_song(path)
    song.word("l0.w1").text = "TWO!"
    save_song(song, path)
    # "TWO!" still normalises to "two", so only the line text is out of date.
    result = runner.invoke(app, ["check", str(path)])
    assert "aligner form" not in result.stdout
    assert "no longer matches its words" in result.stdout


def test_correcting_a_misheard_word_by_hand_is_reported(tmp_path):
    path = _song_file(tmp_path)
    song = load_song(path)
    song.word("l0.w1").text = "purrs"
    save_song(song, path)
    result = runner.invoke(app, ["check", str(path)])
    assert "aligner form" in result.stdout
    assert "re-align" in result.stdout


def test_align_without_lyrics_says_what_to_do(tmp_path):
    result = runner.invoke(app, ["align", str(tmp_path / "a.mp3")])
    assert result.exit_code == 1
    # Errors go to stderr so that piping the JSON path around still works.
    assert "--lyrics" in result.stderr


def test_align_on_unreadable_lyrics_fails_before_loading_a_model(tmp_path):
    result = runner.invoke(
        app, ["align", str(tmp_path / "a.mp3"), "--lyrics", str(tmp_path / "nope.txt")]
    )
    assert result.exit_code == 1
