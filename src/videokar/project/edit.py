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
from difflib import SequenceMatcher

from ..lyrics.normalize import normalize_token
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


MIN_WORD = 0.03
"""Shortest a word may be made. Below this it is a sliver you cannot grab back."""


def set_word_start(song: Song, word_id: str, start: float) -> Edit:
    """Put one word's onset at `start`, keeping its length."""
    word = song.word(word_id)
    if not word.timed:
        raise FixError(f"{word_id} has no timing to move")
    length = word.end - word.start
    return set_word_span(song, word_id, start, round(start + length, 3))


def set_word_span(
    song: Song, word_id: str, start: float | None = None, end: float | None = None
) -> Edit:
    """Set where a word begins and ends, changing how long it lasts.

    Dragging one edge is the natural way to say "this syllable is held" or "this
    one is clipped", so either bound can be set on its own.
    """
    word = song.word(word_id)
    if not word.timed:
        raise FixError(f"{word_id} has no timing to change")
    new_start = round(word.start if start is None else start, 3)
    new_end = round(word.end if end is None else end, 3)
    if new_end - new_start < MIN_WORD:
        raise FixError(
            f"{word_id} would last {new_end - new_start:.3f}s — "
            f"nothing shorter than {MIN_WORD}s, you could not grab it again"
        )

    line = next(ln for ln in song.lines if any(w.id == word_id for w in ln.words))
    _check_word_fits(song, line, word, new_start, new_end)
    word.start, word.end = new_start, new_end
    word.manual = True
    song.refresh_bounds()
    return Edit([line.id], f"{word_id} now {new_start:.2f}-{new_end:.2f}s")


def _check_word_fits(song: Song, line: Line, word: Word, start: float, end: float) -> None:
    """Refuse anything that would overlap a neighbour, in this line or the next.

    The line's own span is derived from its words, so stretching the first or
    last word is really moving the line's edge — which has to answer to the
    lines on either side, not just to the words beside it.
    """
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

    lines = timed_lines(song)
    if line not in lines:
        return
    index = lines.index(line)
    if position == 0 and index > 0 and start < lines[index - 1].end:
        raise FixError(
            f"{word.id} would start at {start:.2f}, before {lines[index - 1].id} "
            f"ends at {lines[index - 1].end:.2f}"
        )
    if position == len(timed) - 1 and index + 1 < len(lines) and end > lines[index + 1].start:
        raise FixError(
            f"{word.id} would end at {end:.2f}, after {lines[index + 1].id} "
            f"starts at {lines[index + 1].start:.2f}"
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


def set_word_text(song: Song, word_id: str, text: str) -> Edit:
    """Correct a word the aligner heard wrong.

    The aligner form is recomputed from the new text rather than left behind,
    and the line's readable copy is rebuilt, so a correction made here does not
    show up as the staleness `check` warns about after a raw file edit.
    """
    text = text.strip()
    if not text:
        raise FixError("a word cannot be emptied — mute the line instead")
    if " " in text:
        raise FixError(f"{text!r} contains a space: a word is one token")

    word = song.word(word_id)
    line = next(ln for ln in song.lines if any(w.id == word_id for w in ln.words))
    was = word.text
    word.text = text
    word.norm = normalize_token(text, lang=song.align.language)
    word.manual = True
    line.rebuild_text()
    return Edit([line.id], f"{word_id}: {was!r} -> {text!r}")


def set_line_text(song: Song, line_id: str, text: str) -> Edit:
    """Retype a whole line, keeping the timings of the words that survive.

    Changing a line can change how many words it has, so the timings have to be
    reassigned. Rather than spreading the new words evenly and throwing away
    everything that was right, the old and new wordings are matched up: a word
    that is still there keeps its timing, and only the ones that changed are
    given new times, interpolated between the words on either side of them.

    Fixing a typo therefore costs nothing, and adding a word squeezes it in
    beside its neighbours instead of shifting the whole line.
    """
    text = " ".join(text.split())
    if not text:
        raise FixError("a line cannot be emptied — mute it instead, so it keeps its place")

    line = song.line(line_id)
    tokens = text.split()
    old = list(line.words)
    old_forms = [normalize_token(w.text, lang=song.align.language) or "" for w in old]
    new_forms = [normalize_token(t, lang=song.align.language) or "" for t in tokens]

    kept: dict[int, Word] = {}
    for tag, i1, i2, j1, _ in SequenceMatcher(
        a=old_forms, b=new_forms, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                kept[j1 + offset] = old[i1 + offset]

    span_start = line.start if line.start is not None else 0.0
    span_end = line.end if line.end is not None else span_start
    words: list[Word] = []
    for position, token in enumerate(tokens):
        source = kept.get(position)
        words.append(
            Word(
                id=f"{line.id}.w{position}",
                text=token,
                norm=normalize_token(token, lang=song.align.language),
                start=source.start if source else None,
                end=source.end if source else None,
                score=source.score if source else None,
                manual=True,
            )
        )

    # A line may grow into the silence after it, but not into the next line.
    following = [
        other for other in timed_lines(song) if other.start is not None and other.start > span_end
    ]
    limit = (following[0].start - MIN_GAP) if following else float("inf")
    _fill_gaps(words, span_start, span_end, limit)
    line.words = words
    line.rebuild_text()
    song.refresh_bounds()
    changed = len(tokens) - len(kept)
    detail = f", {changed} word(s) retimed" if changed else ", every timing kept"
    return Edit([line.id], f"{line_id} is now {text!r}{detail}")


def _tail(share: float) -> float:
    """The sliver left between two words. Proportional, because a fixed gap
    inside a fifty-millisecond hole leaves a word ten milliseconds long."""
    return min(MIN_GAP, share * 0.2)


def _fill_gaps(
    words: list[Word], span_start: float, span_end: float, limit: float = float("inf")
) -> None:
    """Give the words with no timing one, between whatever surrounds them.

    `limit` is how far the line may grow: words appended past the end need room
    that is not inside the line, and the only room there is belongs to the
    silence before the next line.
    """
    anchors = [index for index, word in enumerate(words) if word.timed]
    if not anchors:
        # Nothing survived, so the line is spread across the span it occupied.
        step = (span_end - span_start) / max(len(words), 1)
        for index, word in enumerate(words):
            word.start = round(span_start + index * step, 3)
            word.end = round(span_start + (index + 1) * step - _tail(step), 3)
        return

    # Every run of untimed words is worked out before any of them is given a
    # time: computing them as we go would look at a list that is changing
    # underneath, and the second word of a run would land on top of the first.
    runs: list[list[int]] = []
    current: list[int] = []
    for index, word in enumerate(words):
        if word.timed:
            if current:
                runs.append(current)
                current = []
        else:
            current.append(index)
    if current:
        runs.append(current)

    for run in runs:
        before = max((i for i in anchors if i < run[0]), default=None)
        after = min((i for i in anchors if i > run[-1]), default=None)
        low = words[before].end if before is not None else span_start
        high = words[after].start if after is not None else span_end

        needed = len(run) * (MIN_WORD + MIN_GAP)
        if high - low < needed and after is None:
            # Words appended past the end have nowhere to go inside the line, so
            # it grows — as far as the next line and no further. Without this
            # they came out with start == end, which is not a word at all.
            high = min(low + needed, limit)
        share = max((high - low) / len(run), 0.001)

        for place, index in enumerate(run):
            word = words[index]
            word.start = round(low + share * place, 3)
            word.end = round(low + share * (place + 1) - _tail(share), 3)
            if word.end <= word.start:
                word.end = round(word.start + 0.001, 3)
