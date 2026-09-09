"""Where each word sits on screen.

Laid out once per line, up front, and reused for every frame that shows it —
measuring text is not free and a three minute video at 25fps asks for the same
line several hundred times.

Font size is fixed rather than fitted to the line: a karaoke video whose text
changes size line to line looks broken. A line too wide for the frame wraps at
the size it was given. Shrinking happens only when `min_scale` is explicitly
set below 1.0.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..config.schema import (
    Layout,
    Output,
    TextStyle,
    resolved_margins,
    resolved_outline,
    resolved_size,
)
from ..project.model import Line, Word
from .fonts import resolve_font_path

_MEASURE = ImageDraw.Draw(Image.new("RGBA", (1, 1)))


@lru_cache(maxsize=32)
def load_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


@dataclass(frozen=True, slots=True)
class PlacedWord:
    """One word, positioned. `word` is None for a token with no timing."""

    text: str
    word: Word
    x: float
    y: float
    width: float
    height: float

    @property
    def centre_x(self) -> float:
        return self.x + self.width / 2


@dataclass(frozen=True, slots=True)
class LineLayout:
    line: Line
    font: ImageFont.FreeTypeFont
    style: TextStyle
    words: list[PlacedWord]
    rows: int
    size: int
    """The font size actually used, after any wrap-or-shrink decision."""

    outline_width: int

    def placed(self, word_id: str) -> PlacedWord | None:
        for placed in self.words:
            if placed.word.id == word_id:
                return placed
        return None


def _advance(font: ImageFont.FreeTypeFont, text: str) -> float:
    return _MEASURE.textlength(text, font=font)


def _wrap(words: list[str], font: ImageFont.FreeTypeFont, limit: float) -> list[list[int]]:
    """Greedy wrap, returning word indices per row. Never drops a word."""
    rows: list[list[int]] = [[]]
    width = 0.0
    space = _advance(font, " ")
    for index, text in enumerate(words):
        advance = _advance(font, text)
        extra = advance if not rows[-1] else space + advance
        if rows[-1] and width + extra > limit:
            rows.append([index])
            width = advance
        else:
            rows[-1].append(index)
            width += extra
    return [row for row in rows if row]


def layout_line(line: Line, style: TextStyle, layout: Layout, output: Output) -> LineLayout:
    """Place every word of a line inside the safe area."""
    font_path = resolve_font_path(style.font)
    margin_x, margin_y = resolved_margins(layout, output)
    inset_x = int(output.width * layout.safe_area) + margin_x
    limit = output.width - 2 * inset_x

    texts = [word.text for word in line.words]
    size = resolved_size(style, output)
    font = load_font(font_path, size)
    rows = _wrap(texts, font, limit)

    # Shrinking is off unless asked for: a line drawn smaller than the one
    # before it is more distracting than a line that takes two rows.
    if len(rows) > 1 and style.min_scale < 1.0:
        smaller = max(int(size * style.min_scale), 1)
        candidate = load_font(font_path, smaller)
        if len(_wrap(texts, candidate, limit)) == 1:
            size, font = smaller, candidate
            rows = _wrap(texts, font, limit)

    ascent, descent = font.getmetrics()
    row_height = (ascent + descent) * style.line_spacing
    block_height = row_height * len(rows)

    inset_y = int(output.height * layout.safe_area)
    if layout.y is not None:
        # An exact place, which is what a drag in the preview writes. It wins
        # over the anchor rather than being averaged with it: two ways of saying
        # where something goes, and the more specific one is the answer.
        top = output.height * layout.y - block_height / 2
    elif layout.anchor == "top":
        top = inset_y + margin_y
    elif layout.anchor == "center":
        top = (output.height - block_height) / 2
    else:
        top = output.height - inset_y - margin_y - block_height

    # A margin larger than the frame would push the words out of the picture, and
    # a video with nothing drawn on it is never what the setting meant to ask
    # for. Held inside instead, which the preview then shows.
    top = min(max(top, 0.0), max(0.0, output.height - block_height))

    space = _advance(font, " ")
    placed: list[PlacedWord] = []
    for row_index, row in enumerate(rows):
        widths = [_advance(font, texts[i]) for i in row]
        row_width = sum(widths) + space * (len(row) - 1)
        # Centred on layout.x rather than on the frame, and held inside the safe
        # area: dragged to an edge the words stop at it instead of leaving.
        x = output.width * layout.x - row_width / 2
        x = min(max(x, inset_x), max(inset_x, output.width - inset_x - row_width))
        y = top + row_index * row_height
        for offset, word_index in enumerate(row):
            placed.append(
                PlacedWord(
                    text=texts[word_index],
                    word=line.words[word_index],
                    x=x,
                    y=y,
                    width=widths[offset],
                    height=ascent + descent,
                )
            )
            x += widths[offset] + space

    return LineLayout(
        line=line,
        font=font,
        style=style,
        words=placed,
        rows=len(rows),
        size=size,
        outline_width=resolved_outline(style, size),
    )
