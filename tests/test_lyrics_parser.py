import pytest

from videokar.lyrics import parse_lyrics, parse_lyrics_file
from videokar.lyrics.parser import LyricsError

SAMPLE = """
[Verse 1]
Seven o'clock, she's at the door
(she's not mine, I know)

[Chorus]
Two purrs and then she's gone
"""


def test_sections_and_tags():
    lyrics = parse_lyrics(SAMPLE)
    assert [s.tag for s in lyrics.sections] == ["Verse 1", "Chorus"]
    assert [len(s.lines) for s in lyrics.sections] == [2, 1]


def test_section_tags_are_never_aligned():
    lyrics = parse_lyrics(SAMPLE)
    assert "verse" not in lyrics.alignable_words
    assert "chorus" not in lyrics.alignable_words


def test_parenthesised_line_is_second_voice_and_loses_its_parens():
    line = parse_lyrics(SAMPLE).lines[1]
    assert line.voice == "paren"
    assert line.text == "she's not mine, I know"


def test_mixed_parentheses_stay_main_voice():
    line = parse_lyrics("(one) and (two)").lines[0]
    assert line.voice == "main"
    assert line.text == "(one) and (two)"


def test_unbalanced_parenthesis_stays_main_voice():
    line = parse_lyrics("(she never closes it").lines[0]
    assert line.voice == "main"


def test_lines_before_the_first_tag_get_an_untagged_section():
    lyrics = parse_lyrics("a stray line\n[Verse 1]\nanother one")
    assert lyrics.sections[0].tag is None
    assert lyrics.sections[1].tag == "Verse 1"


def test_line_ids_are_unique_and_sequential_across_sections():
    ids = [line.id for line in parse_lyrics(SAMPLE).lines]
    assert ids == ["l0", "l1", "l2"]


def test_tokens_map_one_to_one_onto_the_visible_words():
    # The prototype asserted this at draw time; here it is a parser guarantee.
    for line in parse_lyrics(SAMPLE).lines:
        assert len(line.tokens) == len(line.text.split())
        assert [t.text for t in line.tokens] == line.text.split()


def test_punctuation_only_token_carries_no_timing():
    line = parse_lyrics("she stays — a while").lines[0]
    assert [t.alignable for t in line.tokens] == [True, True, False, True, True]
    assert line.is_alignable


def test_blank_lines_and_crlf_and_bom_are_tolerated():
    lyrics = parse_lyrics("﻿[Verse 1]\r\n\r\nhello there\r\n")
    assert lyrics.alignable_words == ["hello", "there"]


def test_empty_input_is_an_error():
    with pytest.raises(LyricsError):
        parse_lyrics("[Verse 1]\n[Chorus]\n")


def test_ladycat_lyrics_parse(ladycat_lyrics_path):
    lyrics = parse_lyrics_file(ladycat_lyrics_path)
    assert [s.tag for s in lyrics.sections] == [
        "Verse 1",
        "Pre-Chorus",
        "Chorus",
        "Verse 2",
        "Pre-Chorus",
        "Final Chorus",
        "Outro",
    ]
    assert len(lyrics) == 35
    # The chorus fix from the prototype notes: three lines, not two.
    chorus = next(s for s in lyrics.sections if s.tag == "Chorus")
    assert len(chorus.lines) == 3
    assert all(line.is_alignable for line in lyrics.lines)
    assert lyrics.alignable_words[:3] == ["seven", "o'clock", "she's"]
