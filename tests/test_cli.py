import json

import pytest
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


def _four_line_file(tmp_path):
    song = make_song(
        make_line("l0", ["a", "b", "c"], 10.0),
        make_line("l1", ["d", "e", "f"], 20.0),
        make_line("l2", ["g", "h", "i"], 30.0),
        make_line("l3", ["j", "k", "l"], 40.0),
    )
    return save_song(song, tmp_path / "song.json")


def test_fix_list_shows_the_ids_other_commands_need(tmp_path):
    result = runner.invoke(app, ["fix", "list", str(_four_line_file(tmp_path))])
    assert result.exit_code == 0
    for line_id in ("l0", "l1", "l2", "l3"):
        assert line_id in result.stdout


def test_fix_shift_writes_the_change(tmp_path):
    path = _four_line_file(tmp_path)
    result = runner.invoke(app, ["fix", "shift", str(path), "--line", "l1", "--by", "2"])
    assert result.exit_code == 0
    assert load_song(path).line("l1").start == pytest.approx(22.0)


def test_fix_dry_run_writes_nothing(tmp_path):
    path = _four_line_file(tmp_path)
    result = runner.invoke(
        app, ["fix", "shift", str(path), "--line", "l1", "--by", "2", "--dry-run"]
    )
    assert result.exit_code == 0
    assert load_song(path).line("l1").start == pytest.approx(20.0)


def test_fix_shift_needs_exactly_one_of_by_and_to(tmp_path):
    path = _four_line_file(tmp_path)
    both = runner.invoke(
        app, ["fix", "shift", str(path), "--line", "l1", "--by", "2", "--to", "22"]
    )
    neither = runner.invoke(app, ["fix", "shift", str(path), "--line", "l1"])
    assert both.exit_code == 1 and neither.exit_code == 1


def test_fix_pin_then_shift_keeps_the_anchor_still(tmp_path):
    path = _four_line_file(tmp_path)
    runner.invoke(app, ["fix", "pin", str(path), "--line", "l3"])
    runner.invoke(app, ["fix", "shift", str(path), "--line", "l1", "--by", "2"])
    song = load_song(path)
    assert song.line("l3").pinned
    assert song.line("l3").start == pytest.approx(40.0)
    assert song.line("l2").start > song.line("l1").end


def test_fix_reports_a_refused_edit_and_leaves_the_file_alone(tmp_path):
    path = _four_line_file(tmp_path)
    result = runner.invoke(app, ["fix", "shift", str(path), "--line", "l1", "--by", "-10"])
    assert result.exit_code == 1
    assert "before l0 ends" in result.stderr
    assert load_song(path).line("l1").start == pytest.approx(20.0)


def test_fix_mute_takes_a_line_out_without_deleting_it(tmp_path):
    path = _four_line_file(tmp_path)
    runner.invoke(app, ["fix", "mute", str(path), "--line", "l1"])
    line = load_song(path).line("l1")
    assert not line.sung and line.start is None and line.words_text == "d e f"


def test_config_presets_lists_them(tmp_path):
    result = runner.invoke(app, ["config", "presets"])
    assert result.exit_code == 0
    assert "youtube" in result.stdout and "shorts" in result.stdout


def test_config_init_writes_a_file_that_reads_back(tmp_path):
    from videokar.config import resolve_style

    path = tmp_path / "videokar.toml"
    result = runner.invoke(app, ["config", "init", "-o", str(path), "--preset", "shorts"])
    assert result.exit_code == 0
    assert resolve_style(path).output.height == 1920


def test_config_init_refuses_to_clobber(tmp_path):
    path = tmp_path / "videokar.toml"
    path.write_text("keep me")
    result = runner.invoke(app, ["config", "init", "-o", str(path)])
    assert result.exit_code == 1
    assert path.read_text() == "keep me"
    assert runner.invoke(app, ["config", "init", "-o", str(path), "--force"]).exit_code == 0


def test_config_show_resolves_the_layers(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("[output]\nfps = 48\n")
    result = runner.invoke(
        app, ["config", "show", "-c", str(path), "--preset", "youtube", "--json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["output"]["fps"] == 48
    assert payload["output"]["format"] == "mp4"


def test_config_show_can_print_the_schema():
    result = runner.invoke(app, ["config", "show", "--schema"])
    assert result.exit_code == 0
    assert "$defs" in json.loads(result.stdout)


def test_config_show_reports_a_bad_value(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("[layout]\nanchor = 'sideways'\n")
    result = runner.invoke(app, ["config", "show", "-c", str(path)])
    assert result.exit_code == 1
    assert "layout.anchor" in result.stderr
