"""Turn a finished alignment run into the pivot document."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ..align.confidence import analyse
from ..cache import file_digest
from ..pipeline import AlignedTrack
from .model import AlignInfo, AudioRef, Line, Section, Song, Word

ROUND = 3


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, ROUND)


def build_song(track: AlignedTrack, *, audio_path: str | Path | None = None) -> Song:
    """Assemble the JSON document from an AlignedTrack.

    Word timings arrive as one flat list carrying the index of the line they
    came from, so they are placed back onto the tokens rather than re-derived:
    a token the aligner never saw — punctuation on its own — keeps its place on
    screen with no timing at all.
    """
    lyrics = track.lyrics
    reports = {
        r.index: r
        for r in analyse(
            track.alignment.words,
            group_count=len(lyrics),
            regions=track.regions,
            onsets=track.onsets,
        )
    }

    timings: dict[int, list] = {}
    for timing in track.alignment.words:
        timings.setdefault(timing.group, []).append(timing)

    line_index = 0
    sections: list[Section] = []
    for section in lyrics.sections:
        lines: list[Line] = []
        for parsed in section.lines:
            queue = list(timings.get(line_index, []))
            words: list[Word] = []
            for position, token in enumerate(parsed.tokens):
                timing = queue.pop(0) if token.norm and queue else None
                words.append(
                    Word(
                        id=f"{parsed.id}.w{position}",
                        text=token.text,
                        norm=token.norm,
                        start=_round(timing.start) if timing else None,
                        end=_round(timing.end) if timing else None,
                        score=timing.score if timing else None,
                    )
                )
            report = reports.get(line_index)
            lines.append(
                Line(
                    id=parsed.id,
                    text=parsed.text,
                    voice=parsed.voice,
                    direction=parsed.direction,
                    score=report.score if report else None,
                    flags=[str(flag) for flag in report.flags] if report else [],
                    words=words,
                )
            )
            line_index += 1
        sections.append(Section(id=section.id, tag=section.tag, lines=lines))

    source = Path(audio_path or track.audio.path)
    song = Song(
        audio=AudioRef(
            path=str(source),
            sha256=file_digest(track.audio.path),
            duration=round(track.audio.duration, ROUND),
            sample_rate=track.audio.sample_rate,
            channels=track.audio.channels,
        ),
        align=AlignInfo(
            model=track.alignment.model,
            device=track.alignment.device,
            separator=track.separation.model if track.separation else None,
            language=lyrics.language,
            frame_duration=round(track.alignment.frame_duration, 5),
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            elapsed=round(track.elapsed, 2),
        ),
        vocal_regions=[(_round(r.start), _round(r.end)) for r in track.regions],
        vocal_onsets=list(track.onsets),
        sections=sections,
    )
    song.refresh_bounds()
    return song
