"""Turn a visible lyric token into the form a forced aligner can consume.

The aligner (MMS_FA and friends) works on a small character vocabulary: lowercase
letters plus the apostrophe. Everything else — punctuation, digits, diacritics,
typographic quotes — has to go, but the *visible* token keeps its original shape
so the renderer can draw "o'clock," with the comma attached.

A token that normalizes to nothing (a lone em dash, "…") returns None: it stays
on screen and inherits its timing from a neighbour, but never reaches the aligner.
"""

from __future__ import annotations

import re
import unicodedata

# Aligner vocabulary. Kept explicit rather than derived from the bundle so that
# parsing does not require torch to be installed.
ALPHABET = frozenset("abcdefghijklmnopqrstuvwxyz'")

_APOSTROPHES = "’‘‛ʼ`´"
_TRANSLATIONS = str.maketrans(
    {ch: "'" for ch in _APOSTROPHES}
    | {ch: "" for ch in "‐‑‒–—―-"}  # hyphens/dashes: join the halves
)

_DIGIT_RUN = re.compile(r"\d+")

_ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
)  # fmt: skip
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_SCALES = ((10**9, "billion"), (10**6, "million"), (10**3, "thousand"))


def spell_number_en(n: int) -> str:
    """Spell a non-negative integer in English words, space separated.

    >>> spell_number_en(7)
    'seven'
    >>> spell_number_en(1985)
    'one thousand nine hundred eighty five'
    """
    if n < 0:
        return "minus " + spell_number_en(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, rest = divmod(n, 10)
        return _TENS[tens] + (f" {_ONES[rest]}" if rest else "")
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return f"{_ONES[hundreds]} hundred" + (f" {spell_number_en(rest)}" if rest else "")
    for scale, name in _SCALES:
        if n >= scale:
            count, rest = divmod(n, scale)
            return f"{spell_number_en(count)} {name}" + (
                f" {spell_number_en(rest)}" if rest else ""
            )
    # Beyond a billion, reading it digit by digit is closer to how it gets sung.
    return " ".join(_ONES[int(d)] for d in str(n))


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_token(text: str, lang: str = "en") -> str | None:
    """Reduce one visible token to aligner form, or None when nothing is left.

    Digits are spelled out for English so that "7" aligns against the sung
    "seven". For other languages the digits are dropped rather than mis-spelled,
    which shows up as a low-confidence word instead of a silent wrong match.
    """
    folded = unicodedata.normalize("NFKC", text).translate(_TRANSLATIONS).lower()
    if lang.lower().startswith("en"):
        folded = _DIGIT_RUN.sub(lambda m: f" {spell_number_en(int(m.group()))} ", folded)
    # Number spelling introduces spaces; the token stays a single alignment unit,
    # so the words are joined back up into one character run.
    folded = _strip_accents(folded).replace(" ", "")
    kept = "".join(ch for ch in folded if ch in ALPHABET).strip("'")
    return kept or None
