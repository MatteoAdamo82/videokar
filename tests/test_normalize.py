import pytest

from videokar.lyrics.normalize import normalize_token, spell_number_en


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Seven", "seven"),
        ("o'clock,", "o'clock"),
        ("she’s", "she's"),  # typographic apostrophe
        ("(ladycat)", "ladycat"),
        ("twenty-four", "twentyfour"),
        ("café", "cafe"),
        ("7", "seven"),
        ("1985", "onethousandninehundredeightyfive"),
        ("—", None),
        ("…", None),
        ("'", None),
    ],
)
def test_normalize_token(raw, expected):
    assert normalize_token(raw) == expected


def test_digits_are_dropped_for_other_languages():
    # Better a missing word than an English number sung in Italian.
    assert normalize_token("7", lang="it") is None


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (0, "zero"),
        (7, "seven"),
        (13, "thirteen"),
        (20, "twenty"),
        (42, "forty two"),
        (100, "one hundred"),
        (365, "three hundred sixty five"),
        (1985, "one thousand nine hundred eighty five"),
        (2_000_000, "two million"),
    ],
)
def test_spell_number_en(number, expected):
    assert spell_number_en(number) == expected
