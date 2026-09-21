from pathlib import Path

import pytest

from videokar.render.fonts import (
    FONT_SUFFIXES,
    FontError,
    available_fonts,
    describe_font,
    resolve_font_path,
)


@pytest.fixture(scope="session")
def a_real_font():
    fonts = available_fonts()
    if not fonts:
        pytest.skip("no fonts on this machine to test with")
    return fonts[0]


def test_this_machine_offers_fonts(a_real_font):
    assert a_real_font.path
    assert a_real_font.family


def test_a_font_is_described_by_family_and_style(a_real_font):
    from pathlib import Path

    described = describe_font(Path(a_real_font.path))
    assert described.label.strip()


def test_something_that_is_not_a_font_is_skipped(tmp_path):
    path = tmp_path / "notes.ttf"
    path.write_text("this is not a font")
    assert describe_font(path) is None


def test_the_internal_fallback_faces_are_left_out():
    # Apple names them with a leading dot and does not mean them to be set in.
    assert not any(font.family.startswith(".") for font in available_fonts())


def test_the_list_has_no_duplicates():
    labels = [font.label for font in available_fonts()]
    assert len(labels) == len(set(labels))


def test_a_font_in_the_working_folder_wins_over_the_system_copy(tmp_path, a_real_font):
    # Same family name in two places: the one put next to the song is the one
    # that was meant, so it is the one offered.
    import shutil
    from pathlib import Path

    if Path(a_real_font.path).suffix.lower() not in FONT_SUFFIXES:
        pytest.skip("nothing copyable")
    shutil.copy(a_real_font.path, tmp_path / "dropped.ttf")
    offered = {font.label: font.path for font in available_fonts(tmp_path)}
    assert offered[a_real_font.label].endswith("dropped.ttf")


def test_a_missing_font_file_says_so(tmp_path):
    with pytest.raises(FontError, match="not found"):
        resolve_font_path(str(tmp_path / "nope.ttf"))


def test_fonts_in_folders_under_a_system_folder_are_found(a_real_font, tmp_path, monkeypatch):
    # How Linux lays them out: /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf.
    # Reading only the top level found nothing there, and left the dialog's
    # font list empty on every Linux machine.
    import shutil

    from videokar.render import fonts

    nested = tmp_path / "share" / "fonts" / "truetype" / "somefamily"
    nested.mkdir(parents=True)
    shutil.copy(a_real_font.path, nested / "Face.ttf")
    monkeypatch.setattr(fonts, "FONT_DIRECTORIES", (str(tmp_path / "share" / "fonts"),))
    fonts._scan.cache_clear()
    try:
        found = fonts.available_fonts()
    finally:
        fonts._scan.cache_clear()
    assert [Path(f.path).name for f in found] == ["Face.ttf"]


def test_the_working_folder_is_read_flat(a_real_font, tmp_path, monkeypatch):
    # A font put next to the song on purpose sits at the top. One that has been
    # moved into .trash, or is buried in some render's folder, is not on offer.
    import shutil

    from videokar.render import fonts

    shutil.copy(a_real_font.path, tmp_path / "Chosen.ttf")
    (tmp_path / ".trash").mkdir()
    shutil.copy(a_real_font.path, tmp_path / ".trash" / "Discarded.ttf")
    (tmp_path / "renders").mkdir()
    shutil.copy(a_real_font.path, tmp_path / "renders" / "Buried.ttf")
    monkeypatch.setattr(fonts, "FONT_DIRECTORIES", ())
    fonts._scan.cache_clear()
    try:
        found = fonts.available_fonts(tmp_path)
    finally:
        fonts._scan.cache_clear()
    assert [Path(f.path).name for f in found] == ["Chosen.ttf"]


def test_hidden_folders_are_passed_over(a_real_font, tmp_path, monkeypatch):
    import shutil

    from videokar.render import fonts

    (tmp_path / "fonts" / ".cache").mkdir(parents=True)
    shutil.copy(a_real_font.path, tmp_path / "fonts" / ".cache" / "Hidden.ttf")
    monkeypatch.setattr(fonts, "FONT_DIRECTORIES", (str(tmp_path / "fonts"),))
    fonts._scan.cache_clear()
    try:
        assert fonts.available_fonts() == []
    finally:
        fonts._scan.cache_clear()
