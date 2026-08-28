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
