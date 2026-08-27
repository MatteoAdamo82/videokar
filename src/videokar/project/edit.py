"""Repairing timings by hand.

Alignment on sung audio drifts in blocks, not in single words: a whole chorus
lands three seconds early while the lines on either side are right. So the unit
of repair is a line, and moving one has to carry the lines after it — otherwise
every correction leaves a hole or an overlap behind.

Carrying them blindly is wrong too. On the reference track the two lines after
the bad chorus are already correct, and a plain forward ripple would push them
out of place to fix the ones before. Hence anchors: a line marked `pinned` is
one you have declared correct, a shift never moves it, and the lines between the
edit and the next anchor are redistributed into whatever span is left.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Line, Song, Word

MIN_GAP = 0.01
"""Smallest silence left between two lines, so they cannot touch or invert."""


class FixError(RuntimeError):
    """The edit would produce a timeline that cannot be rendered."""


@dataclass(frozen=True, slots=True)
class Edit:
    """What an operation did, for reporting back."""

    moved: list[str]
    """Line ids whose timing changed."""

    description: str


def timed_lines(song: Song) -> list[Line]:
    """Sung lines that have timings, in playing order."""
    return [
        line
        for line in song.lines
        if line.sung and line.start is not None and line.end is not None
    ]


def _shift_words(line: Line, delta: float) -> None:
    for word in line.words:
        if word.timed:
            word.start = round(word.start + delta, 3)
            word.end = round(word.end + delta, 3)
            word.manual = True


def _remap_words(line: Line, old_lo: float, old_hi: float, new_lo: float, new_hi: float) -> None:
    """Linearly rescale a line's words from one span onto another."""
    old_span = old_hi - old_lo
    scale = (new_hi - new_lo) / old_span if old_span > 0 else 1.0
    for word in line.words:
        if not word.timed:
            continue
        word.start = round(new_lo + (word.start - old_lo) * scale, 3)
        word.end = round(new_lo + (word.end - old_lo) * scale, 3)
        word.manual = True


def _index_of(lines: list[Line], line_id: str) -> int:
    for index, line in enumerate(lines):
        if line.id == line_id:
            return index
    raise FixError(f"no timed line {line_id!r} — it may be unsung or have no timings")


def shift_line(song: Song, line_id: str, delta: float) -> Edit:
    """Move a line by `delta` seconds and carry the lines after it.

    The ripple stops at the next pinned line: the lines in between are squeezed
    or stretched into the span that is left. With no anchor ahead, everything
    after the edit simply moves with it.
    """
    lines = timed_lines(song)
    index = _index_of(lines, line_id)
    line = lines[index]

    new_start = line.start + delta
    if index > 0 and new_start < lines[index - 1].end + MIN_GAP:
        previous = lines[index - 1]
        raise FixError(
            f"{line_id} would start at {new_start:.2f}, before {previous.id} ends at "
            f"{previous.end:.2f} — move {previous.id} first, or use a smaller shift"
        )
    if line.pinned:
        raise FixError(f"{line_id} is pinned — unpin it first if you mean to move it")

    anchor_index = next(
        (i for i in range(index + 1, len(lines)) if lines[i].pinned),
        None,
    )

    if anchor_index is None:
        for following in lines[index:]:
            _shift_words(following, delta)
        moved = [ln.id for ln in lines[index:]]
        tail = f" and the {len(moved) - 1} lines after it" if len(moved) > 1 else ""
        song.refresh_bounds()
        return Edit(moved, f"moved {line_id} by {delta:+.2f}s{tail}")

    anchor = lines[anchor_index]
    _shift_words(line, delta)
    # The line's own start/end are cached fields, so they have to catch up
    # before they can be used to work out the room left behind it.
    song.refresh_bounds()
    between = lines[index + 1 : anchor_index]
    moved = [line_id]

    if line.end + MIN_GAP > anchor.start:
        raise FixError(
            f"{line_id} would run to {line.end:.2f}, past the anchor {anchor.id} at "
            f"{anchor.start:.2f} — unpin {anchor.id}, or move it too"
        )

    if between:
        old_lo, old_hi = between[0].start, anchor.start
        # The shifted line's own end has already moved, so the span the
        # in-between lines have to share starts just after it.
        new_lo, new_hi = line.end + MIN_GAP, anchor.start
        if new_hi - new_lo <= MIN_GAP:
            raise FixError(
                f"no room left between {line_id} and the anchor {anchor.id} at "
                f"{anchor.start:.2f} — unpin {anchor.id}, or move it too"
            )
        for following in between:
            _remap_words(following, old_lo, old_hi, new_lo, new_hi)
            moved.append(following.id)

    song.refresh_bounds()
    squeezed = f", {len(between)} lines redistributed up to {anchor.id}" if between else ""
    return Edit(moved, f"moved {line_id} by {delta:+.2f}s{squeezed}")


def set_line_start(song: Song, line_id: str, start: float) -> Edit:
    """Move a line so it begins at `start`, carrying the lines after it."""
    lines = timed_lines(song)
    line = lines[_index_of(lines, line_id)]
    return shift_line(song, line_id, round(start - line.start, 3))


def shift_word(song: Song, word_id: str, delta: float) -> Edit:
    """Move one word. Its neighbours stay where they are."""
    word = song.word(word_id)
    if not word.timed:
        raise FixError(f"{word_id} has no timing to move")
    return set_word_start(song, word_id, round(word.start + delta, 3))


def set_word_start(song: Song, word_id: str, start: float) -> Edit:
    """Put one word's onset at `start`, keeping its length."""
    word = song.word(word_id)
    if not word.timed:
        raise FixError(f"{word_id} has no timing to move")
    line = next(ln for ln in song.lines if any(w.id == word_id for w in ln.words))
    length = word.end - word.start
    _check_word_fits(line, word, start, start + length)
    word.start, word.end = round(start, 3), round(start + length, 3)
    word.manual = True
    song.refresh_bounds()
    return Edit([line.id], f"moved {word_id} to {start:.2f}s")


def _check_word_fits(line: Line, word: Word, start: float, end: float) -> None:
    timed = [w for w in line.words if w.timed]
    position = timed.index(word)
    if position > 0 and start < timed[position - 1].end:
        raise FixError(
            f"{word.id} would start at {start:.2f}, before {timed[position - 1].id} "
            f"ends at {timed[position - 1].end:.2f}"
        )
    if position + 1 < len(timed) and end > timed[position + 1].start:
        raise FixError(
            f"{word.id} would end at {end:.2f}, after {timed[position + 1].id} "
            f"starts at {timed[position + 1].start:.2f}"
        )


def set_pinned(song: Song, line_id: str, pinned: bool) -> Edit:
    """Declare a line's timing correct, or stop declaring it."""
    line = song.line(line_id)
    line.pinned = pinned
    return Edit([], f"{'pinned' if pinned else 'unpinned'} {line_id}")


def set_sung(song: Song, line_id: str, sung: bool) -> Edit:
    """Take a line out of the video, or put it back.

    An unsung line keeps its place in the file and its words, but loses its
    timing and is skipped by the renderer — for a lyric that never made the
    recording.
    """
    line = song.line(line_id)
    line.sung = sung
    if not sung:
        for word in line.words:
            word.start = word.end = None
    song.refresh_bounds()
    return Edit([line_id], f"marked {line_id} as {'sung' if sung else 'not sung'}")


def stretch(song: Song, first_id: str, last_id: str, start: float, end: float) -> Edit:
    """Fit a run of lines into an exact span, keeping their relative spacing.

    The repair for a block that is both misplaced and misshapen: give it the
    span you know it occupies and let the words inside divide it up.
    """
    lines = timed_lines(song)
    first, last = _index_of(lines, first_id), _index_of(lines, last_id)
    if last < first:
        first, last = last, first
    chosen = lines[first : last + 1]
    if end - start <= MIN_GAP:
        raise FixError(f"{start:.2f}-{end:.2f} is not a usable span")
    if first > 0 and start < lines[first - 1].end + MIN_GAP:
        raise FixError(f"{start:.2f} overlaps {lines[first - 1].id}")
    if last + 1 < len(lines) and end > lines[last + 1].start - MIN_GAP:
        raise FixError(f"{end:.2f} overlaps {lines[last + 1].id}")

    old_lo, old_hi = chosen[0].start, chosen[-1].end
    for line in chosen:
        _remap_words(line, old_lo, old_hi, start, end)
    song.refresh_bounds()
    return Edit(
        [line.id for line in chosen],
        f"fitted {len(chosen)} lines into {start:.2f}-{end:.2f}s",
    )
