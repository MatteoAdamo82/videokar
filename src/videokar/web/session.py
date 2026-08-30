"""What the page is looking at, and what it can say about it.

The session is the one piece of state the routes share. It holds the document
that is open, the folder it lives in, the undo history and the background jobs
— and it answers the two questions every route asks: which document, and where
is its audio.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..project import check_song, load_song, save_song
from .jobs import Jobs

UNDO_DEPTH = 50
"""How many edits back you can step. Documents are small; fifty is plenty and
still nothing next to the audio already in memory."""

SETTINGS = "videokar.toml"
"""Where the export dialog keeps its choices — the same file the CLI reads, so
what the view produces can be reproduced from a terminal."""

MAX_UPLOAD = 200 * 1024 * 1024
"""Refuse anything past this rather than filling the disk with a mistake."""


def audio_for(song, song_path: Path) -> Path | None:
    """Find the audio a document names, relative to the document if need be."""
    candidate = Path(song.audio.path)
    for option in (candidate, song_path.parent / candidate, song_path.parent / candidate.name):
        if option.exists():
            return option
    return None



def payload(song, song_path: Path) -> dict[str, Any]:
    """The document plus the freshly recomputed flags, as the page wants it."""
    report = check_song(song, apply=True)
    distances = {
        report.line_ids[line.index]: line.onset_distance
        for line in report.reports
        if line.onset_distance is not None
    }
    return {
        "song": song.model_dump(by_alias=True),
        "path": str(song_path),
        "issues": [
            {"level": i.level, "code": i.code, "message": i.message, "line": i.line_id}
            for i in report.issues
        ],
        "suspicious": report.suspicious_line_ids,
        # How far each line sits from the nearest point the voice comes in, so
        # the view can say which way to drag it rather than only that it is odd.
        "off_the_attack": distances,
    }



class Session:
    """What the page is looking at, which it can change while running."""

    def __init__(
        self,
        song_path: Path | None,
        workdir: Path,
        *,
        audio_path: Path | None = None,
        vocals_path: Path | None = None,
    ) -> None:
        self.song_path = Path(song_path) if song_path else None
        self.workdir = Path(workdir)
        # Resolved once at startup and possibly outside the working directory,
        # so they win over what the document names — but only for that document.
        self.opened = self.song_path
        self.audio_override = Path(audio_path) if audio_path else None
        self.vocals_override = Path(vocals_path) if vocals_path else None
        self.history: list[str] = []
        self.jobs = Jobs()
        self.reserved: set[str] = set()
        """Output names handed out but not yet written."""

    def require(self) -> Path:
        if self.song_path is None:
            raise FileNotFoundError("no song open — pick one, or make one from an audio file")
        return self.song_path

    def current(self) -> Path:
        """The open document, as a refusal the page can show rather than a 500."""
        try:
            return self.require()
        except FileNotFoundError as exc:
            raise HTTPException(409, str(exc)) from exc

    def audio_of(self, path: Path) -> Path | None:
        if self.opened and path == self.opened and self.audio_override:
            return self.audio_override
        return audio_for(load_song(path), path)

    def vocals_of(self, found: Path | None) -> Path | None:
        """The isolated stem, when the audio is the one it was made from."""
        return self.vocals_override if found == self.audio_override else None

    def open(self, path: Path) -> None:
        load_song(path)  # refuse to switch to something that will not load
        self.song_path = path
        self.history.clear()

    def ensure_onsets(self, audio: Path | None) -> None:
        """Fill in the vocal attacks for a document written before they existed."""
        if self.song_path is None or audio is None:
            return
        song = load_song(self.song_path)
        if song.vocal_onsets:
            return
        from ..pipeline import onsets_for  # noqa: PLC0415

        song.vocal_onsets = onsets_for(audio)
        save_song(song, self.song_path)
