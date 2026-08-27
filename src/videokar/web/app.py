"""A local page for fixing sync by hand.

Every edit goes through the same operations the `fix` command uses, so the
anchor rules, the guards against inverting the timeline and the `manual` marking
behave identically whether you drag a line or type a command. The server is a
thin layer over `videokar.project.edit` and the document on disk stays the
source of truth: it is rewritten after each accepted edit, so closing the tab
never loses work and the file can be edited from the terminal in between.

Bound to localhost. It reads and writes a file on this machine and has no
authentication, so it is not something to expose.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..audio.peaks import peaks_for
from ..project import check_song, load_song, save_song
from ..project.edit import (
    FixError,
    set_line_start,
    set_pinned,
    set_sung,
    set_word_span,
    set_word_start,
    set_word_text,
    shift_line,
    stretch,
)

logger = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"

UNDO_DEPTH = 50
"""How many edits back you can step. Documents are small; fifty is plenty and
still nothing next to the audio already in memory."""


class EditRequest(BaseModel):
    """One operation from the page.

    Declared at module level on purpose: postponed annotations turn the handler
    signature into a string, and FastAPI resolves it against module globals, so
    a model defined inside the factory is invisible and every request comes back
    as a validation error.
    """

    op: str
    line: str | None = None
    word: str | None = None
    to: float | None = None
    by: float | None = None
    start: float | None = None
    end: float | None = None
    first: str | None = None
    last: str | None = None
    text: str | None = None
    value: bool | None = None


class WebUnavailableError(RuntimeError):
    """The web extra is not installed."""


def _require_fastapi():
    try:
        import fastapi  # noqa: F401, PLC0415
        import uvicorn  # noqa: F401, PLC0415
    except ImportError as exc:  # pragma: no cover - depends on install extras
        raise WebUnavailableError(
            'the web extra is not installed — pip install "videokar[web]"'
        ) from exc


def _payload(song, song_path: Path) -> dict[str, Any]:
    """The document plus the freshly recomputed flags, as the page wants it."""
    report = check_song(song, apply=True)
    return {
        "song": song.model_dump(by_alias=True),
        "path": str(song_path),
        "issues": [
            {"level": i.level, "code": i.code, "message": i.message, "line": i.line_id}
            for i in report.issues
        ],
        "suspicious": report.suspicious_line_ids,
    }


def create_app(song_path: Path, audio_path: Path | None = None, vocals_path: Path | None = None):
    """Build the FastAPI application for one document."""
    _require_fastapi()
    from fastapi import FastAPI, HTTPException  # noqa: PLC0415
    from fastapi.responses import FileResponse, HTMLResponse  # noqa: PLC0415

    song_path = Path(song_path)
    app = FastAPI(title="videokar", docs_url=None, redoc_url=None)
    # Dragging is exploratory, so every accepted edit keeps the document as it
    # was. Whole snapshots rather than inverse operations: retyping a word and
    # stretching a run do not invert cleanly, and a document is a few hundred
    # kilobytes of text.
    history: list[str] = []

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/api/song")
    def get_song() -> dict[str, Any]:
        return _payload(load_song(song_path), song_path)

    @app.get("/api/peaks")
    def get_peaks() -> dict[str, Any]:
        if audio_path is None:
            raise HTTPException(404, "the audio this document names could not be found")
        return peaks_for(audio_path, vocals_path=vocals_path)

    @app.get("/api/audio")
    def get_audio() -> Any:
        if audio_path is None:
            raise HTTPException(404, "the audio this document names could not be found")
        return FileResponse(audio_path)

    @app.post("/api/edit")
    def apply_edit(request: EditRequest) -> dict[str, Any]:
        before = song_path.read_text(encoding="utf-8")
        song = load_song(song_path)
        try:
            edit = _dispatch(song, request)
        except (FixError, KeyError) as exc:
            # A refused edit is the normal way to learn a drag was impossible,
            # so it comes back as a message for the page rather than a 500. One
            # status for every refusal, including an id that does not exist:
            # the page shows the reason either way, and the operations disagree
            # about which exception an unknown id raises. KeyError stringifies
            # its argument with repr, so only that one needs unwrapping.
            detail = exc.args[0] if isinstance(exc, KeyError) else str(exc)
            raise HTTPException(409, str(detail)) from exc

        history.append(before)
        del history[:-UNDO_DEPTH]
        save_song(song, song_path)
        result = _payload(song, song_path)
        result["edit"] = {"description": edit.description, "moved": edit.moved}
        result["undo_depth"] = len(history)
        return result

    @app.post("/api/undo")
    def undo() -> dict[str, Any]:
        if not history:
            raise HTTPException(409, "nothing to undo")
        song_path.write_text(history.pop(), encoding="utf-8")
        result = _payload(load_song(song_path), song_path)
        result["edit"] = {"description": "undone", "moved": []}
        result["undo_depth"] = len(history)
        return result

    return app


def _dispatch(song, request: EditRequest) -> Any:
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
    if op == "pin":
        return set_pinned(song, request.line, bool(request.value))
    if op == "mute":
        return set_sung(song, request.line, bool(request.value))
    if op == "stretch":
        return stretch(song, request.first, request.last, request.start, request.end)
    raise FixError(f"unknown operation {op!r}")


def serve(
    song_path: Path,
    *,
    audio_path: Path | None = None,
    vocals_path: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8712,
) -> None:  # pragma: no cover - starts a server
    _require_fastapi()
    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        create_app(song_path, audio_path, vocals_path),
        host=host,
        port=port,
        log_level="warning",
    )
