import json

from typer.testing import CliRunner

from videokar import __version__
from videokar.cli import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_lyrics_table(ladycat_lyrics_path):
    result = runner.invoke(app, ["lyrics", str(ladycat_lyrics_path)])
    assert result.exit_code == 0
    assert "Verse 1" in result.stdout
    assert "35" in result.stdout


def test_lyrics_json(ladycat_lyrics_path):
    result = runner.invoke(app, ["lyrics", str(ladycat_lyrics_path), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [s["tag"] for s in payload["sections"]][0] == "Verse 1"


def test_missing_file_exits_nonzero(tmp_path):
    result = runner.invoke(app, ["lyrics", str(tmp_path / "nope.txt")])
    assert result.exit_code == 1
