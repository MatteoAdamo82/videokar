"""Lyrics parsing: Suno-style text in, alignable tokens out."""

from .normalize import normalize_token, spell_number_en
from .parser import (
    ParsedLine,
    ParsedLyrics,
    ParsedSection,
    Token,
    parse_lyrics,
    parse_lyrics_file,
)

__all__ = [
    "ParsedLine",
    "ParsedLyrics",
    "ParsedSection",
    "Token",
    "normalize_token",
    "parse_lyrics",
    "parse_lyrics_file",
    "spell_number_en",
]
