"""What the view can open, and how a new song gets made.

The view is meant to be the way in, not a thing you point at a file you already
made on the command line, so it needs to list documents and build one from an
audio file plus its lyrics.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from ..align.confidence import Flag
from ..lyrics import parse_lyrics
from ..project import build_song, load_song, save_song
from ..project.io import ProjectError

logger = logging.getLogger(__name__)

AUDIO_SUFFIXES = {".mp3", ".wav", ".aif", ".aiff", ".m4a", ".flac", ".ogg"}
SPRITE_SUFFIXES = {".png"}
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class Entry:
    """One document the view can open."""

    path: Path
    title: str
    lines: int
    flagged: int
    duration: float

    def as_dict(self) -> dict:
        return {
            "path": str(self.path),
            "name": self.path.name,
            "title": self.title,
            "lines": self.lines,
            "flagged": self.flagged,
            "duration": round(self.duration, 2),
        }


def safe_name(name: str) -> str:
    """A filename from user input that cannot escape the working directory."""
    cleaned = _SAFE.sub("-", Path(name).name).strip("-.")
    return cleaned or "song"


def scan(directory: Path) -> list[Entry]:
    """Every videokar document in a directory, newest first."""
    entries: list[Entry] = []
    for path in sorted(directory.glob("*.json"), key=lambda p: -p.stat().st_mtime):
        try:
            song = load_song(path)
        except (OSError, ProjectError):
            # Any other JSON in the folder is simply not ours.
            continue
        entries.append(
            Entry(
                path=path,
                title=Path(song.audio.path).stem,
                lines=len(song.lines),
                flagged=sum(1 for line in song.lines if line.flags),
                duration=song.audio.duration,
            )
        )
    return entries


def align_to_document(
    audio_path: Path,
    lyrics_text: str,
    destination: Path,
    *,
    language: str = "en",
    separate: bool = True,
    device: str = "auto",
    on_step=None,
) -> Path:
    """Run the pipeline over an audio file and write the pivot document."""
    from ..pipeline import run_alignment  # noqa: PLC0415

    def step(message: str, progress: float) -> None:
        if on_step:
            on_step(message, progress)

    step("reading the lyrics", 0.05)
    lyrics = parse_lyrics(lyrics_text, language=language)

    step("isolating the vocal — this is the slow part" if separate else "decoding", 0.15)
    track = run_alignment(
        audio_path, lyrics, separate=separate, device=device, use_cache=True
    )

    step("writing the document", 0.9)
    song = build_song(track, audio_path=audio_path)
    save_song(song, destination)

    flagged = sum(1 for line in song.lines if Flag.LOW_SCORE.value in line.flags or line.flags)
    step(f"{len(song.words)} words over {len(song.lines)} lines, {flagged} flagged", 1.0)
    return destination


def sprites(directory: Path) -> list[str]:
    """PNGs in the working directory, offered as things to bounce."""
    return sorted(
        path.name
        for path in directory.glob("*.png")
        if path.is_file() and path.stat().st_size > 0
    )
