"""One operation from the page, mapped onto the same edits `fix` calls.

The page and the command line go through the same functions, so the anchor
rules, the guards against inverting the timeline and the `manual` marking
behave identically whether you drag a line or type a command.
"""

from __future__ import annotations

from typing import Any

from ..project.edit import (
    FixError,
    set_line_start,
    set_line_text,
    set_pinned,
    set_sung,
    set_word_span,
    set_word_start,
    set_word_text,
    shift_line,
    stretch,
)
from .models import EditRequest


def dispatch(song, request: EditRequest) -> Any:
    """Map a request onto the same operations the `fix` command calls."""
    op = request.op
    if op == "shift_line":
        if request.to is not None:
            return set_line_start(song, request.line, request.to)
        return shift_line(song, request.line, request.by or 0.0)
    if op == "move_word":
        return set_word_start(song, request.word, request.to)
    if op == "resize_word":
        return set_word_span(song, request.word, request.start, request.end)
    if op == "set_text":
        return set_word_text(song, request.word, request.text or "")
    if op == "set_line_text":
        return set_line_text(song, request.line, request.text or "")
    if op == "pin":
        return set_pinned(song, request.line, bool(request.value))
    if op == "mute":
        return set_sung(song, request.line, bool(request.value))
    if op == "stretch":
        return stretch(song, request.first, request.last, request.start, request.end)
    raise FixError(f"unknown operation {op!r}")
