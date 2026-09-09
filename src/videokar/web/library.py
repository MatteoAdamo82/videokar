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
from ..render.background import CLIP_SUFFIXES as _CLIP_SUFFIXES

logger = logging.getLogger(__name__)

# A guard against an obvious mistake, not a codec list: ffprobe decides what it
# can actually read, and says so clearly when it cannot.
AUDIO_SUFFIXES = {
    ".mp3", ".wav", ".aif", ".aiff", ".m4a", ".flac", ".ogg", ".oga",
    ".opus", ".aac", ".wma", ".mp4", ".caf", ".alac", ".aifc",
}  # fmt: skip
SPRITE_SUFFIXES = {".png"}

PICTURE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
"""Stills Pillow reads, offered as something to put behind the words."""

CLIP_SUFFIXES = _CLIP_SUFFIXES
"""Clips ffmpeg composites while encoding. The renderer decides the list; it is
the half that has to tell a still from a clip when it draws one."""

BACKGROUND_SUFFIXES = PICTURE_SUFFIXES | CLIP_SUFFIXES
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


def backgrounds(directory: Path) -> list[dict[str, str]]:
    """Stills and clips in the working directory, each said to be which.

    Which one it is decides where it gets drawn — a still by Pillow into every
    frame, a clip by ffmpeg while encoding — so the page is told rather than
    left to guess from the name.
    """
    found = [
        {"name": path.name, "kind": "video" if path.suffix.lower() in CLIP_SUFFIXES else "image"}
        for path in sorted(directory.iterdir())
        if path.is_file()
        and path.suffix.lower() in BACKGROUND_SUFFIXES
        and path.stat().st_size > 0
    ]
    return found


def next_output(directory: Path, stem: str, suffix: str, taken: set[str] | None = None) -> Path:
    """A name no earlier export has taken.

    Every export used to overwrite one filename, so a copy downloaded earlier
    was indistinguishable from the one just made — and since the timings get
    corrected between exports, an old file looks exactly like a new one that has
    drifted.

    `taken` holds names already handed out this session: the file itself does
    not exist until the render starts, so two exports asked for in quick
    succession would otherwise be given the same one.
    """
    taken = taken if taken is not None else set()
    for number in range(1, 10000):
        candidate = directory / f"{stem}-{number}{suffix}"
        if not candidate.exists() and candidate.name not in taken:
            return candidate
    raise RuntimeError(f"ten thousand exports of {stem}; something is wrong")


TRASH = ".trash"


def discard(path: Path, workdir: Path, *, media: bool = False) -> list[str]:
    """Take a song out of the folder, keeping it recoverable.

    Moved into a .trash subfolder rather than deleted. This is somebody's work,
    the button is one click, and a mistake here costs an alignment run at best.

    `media` also removes the audio the document names, which is only safe when
    nothing else in the folder refers to it — so that is checked rather than
    assumed.
    """
    if path.parent.resolve() != workdir.resolve():
        raise ValueError("that file is outside the working directory")

    targets = [path]
    if media:
        try:
            audio = Path(load_song(path).audio.path)
        except (OSError, ProjectError):
            audio = None
        if audio is not None:
            local = workdir / audio.name
            others = [
                other
                for other in workdir.glob("*.json")
                if other != path and _names_audio(other, audio.name)
            ]
            if local.is_file() and not others:
                targets.append(local)

    bin_folder = workdir / TRASH
    bin_folder.mkdir(exist_ok=True)
    moved = []
    for target in targets:
        destination = bin_folder / target.name
        for number in range(1, 1000):
            if not destination.exists():
                break
            destination = bin_folder / f"{target.stem}-{number}{target.suffix}"
        target.rename(destination)
        moved.append(target.name)
    return moved


def _names_audio(document: Path, name: str) -> bool:
    try:
        return Path(load_song(document).audio.path).name == name
    except (OSError, ProjectError):
        return False
