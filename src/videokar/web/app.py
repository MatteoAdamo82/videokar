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

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from ..audio.peaks import peaks_for
from ..config import ConfigError, available_presets, resolve_style
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
from ..project.io import ProjectError
from . import library
from .jobs import Jobs

logger = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"

MAX_UPLOAD = 200 * 1024 * 1024
"""Refuse anything past this rather than filling the disk with a mistake."""

UNDO_DEPTH = 50
"""How many edits back you can step. Documents are small; fifty is plenty and
still nothing next to the audio already in memory."""


class RenderRequest(BaseModel):
    preset: str | None = None
    format: str | None = None
    width: int | None = None
    height: int | None = None
    fps: int | None = None


class OpenRequest(BaseModel):
    path: str


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


class Session:
    """What the page is looking at, which it can change while running."""

    def __init__(self, song_path: Path | None, workdir: Path) -> None:
        self.song_path = Path(song_path) if song_path else None
        self.workdir = Path(workdir)
        self.history: list[str] = []
        self.jobs = Jobs()

    def require(self) -> Path:
        if self.song_path is None:
            raise FileNotFoundError("no song open — pick one, or make one from an audio file")
        return self.song_path

    def open(self, path: Path) -> None:
        load_song(path)  # refuse to switch to something that will not load
        self.song_path = path
        self.history.clear()


def _audio_for(song, song_path: Path) -> Path | None:
    """Find the audio a document names, relative to the document if need be."""
    candidate = Path(song.audio.path)
    for option in (candidate, song_path.parent / candidate, song_path.parent / candidate.name):
        if option.exists():
            return option
    return None


def create_app(
    song_path: Path | None = None,
    audio_path: Path | None = None,
    vocals_path: Path | None = None,
    workdir: Path | None = None,
):
    """Build the FastAPI application."""
    base = Path(workdir) if workdir else (Path(song_path).parent if song_path else Path.cwd())
    session = Session(song_path, base)
    app = FastAPI(title="videokar", docs_url=None, redoc_url=None)

    def current() -> Path:
        try:
            return session.require()
        except FileNotFoundError as exc:
            raise HTTPException(409, str(exc)) from exc

    def audio_of(path: Path) -> Path | None:
        # The paths handed in at startup win, since they were resolved once and
        # may point outside the working directory.
        if song_path and path == Path(song_path) and audio_path:
            return audio_path
        return _audio_for(load_song(path), path)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/api/song")
    def get_song() -> dict[str, Any]:
        return _payload(load_song(current()), current())

    @app.get("/api/library")
    def get_library() -> dict[str, Any]:
        return {
            "workdir": str(session.workdir),
            "open": str(session.song_path) if session.song_path else None,
            "songs": [entry.as_dict() for entry in library.scan(session.workdir)],
            "presets": available_presets(),
        }

    @app.post("/api/open")
    def open_song(request: OpenRequest) -> dict[str, Any]:
        path = Path(request.path)
        if path.parent.resolve() != session.workdir.resolve():
            raise HTTPException(403, "that file is outside the working directory")
        try:
            session.open(path)
        except (OSError, ProjectError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return _payload(load_song(path), path)

    @app.get("/api/peaks")
    def get_peaks() -> dict[str, Any]:
        path = current()
        found = audio_of(path)
        if found is None:
            raise HTTPException(404, "the audio this document names could not be found")
        return peaks_for(found, vocals_path=vocals_path if found == audio_path else None)

    @app.get("/api/audio")
    def get_audio() -> Any:
        found = audio_of(current())
        if found is None:
            raise HTTPException(404, "the audio this document names could not be found")
        return FileResponse(found)

    @app.post("/api/edit")
    def apply_edit(request: EditRequest) -> dict[str, Any]:
        path = current()
        before = path.read_text(encoding="utf-8")
        song = load_song(path)
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

        session.history.append(before)
        del session.history[:-UNDO_DEPTH]
        save_song(song, path)
        result = _payload(song, path)
        result["edit"] = {"description": edit.description, "moved": edit.moved}
        result["undo_depth"] = len(session.history)
        return result

    @app.post("/api/undo")
    def undo() -> dict[str, Any]:
        path = current()
        if not session.history:
            raise HTTPException(409, "nothing to undo")
        path.write_text(session.history.pop(), encoding="utf-8")
        result = _payload(load_song(path), path)
        result["edit"] = {"description": "undone", "moved": []}
        result["undo_depth"] = len(session.history)
        return result

    @app.post("/api/songs")
    async def create_song(
        audio: UploadFile = File(...),
        lyrics: str = Form(...),
        language: str = Form("en"),
        separate: bool = Form(True),
    ) -> dict[str, Any]:
        """Take an audio file and its lyrics, and align them in the background."""
        if not lyrics.strip():
            raise HTTPException(422, "the lyrics are empty")
        name = library.safe_name(audio.filename or "song")
        if Path(name).suffix.lower() not in library.AUDIO_SUFFIXES:
            raise HTTPException(
                422, f"{name!r} is not an audio file ffmpeg is likely to read"
            )

        session.workdir.mkdir(parents=True, exist_ok=True)
        destination = session.workdir / name
        size = 0
        with open(destination, "wb") as handle:
            while chunk := await audio.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    handle.close()
                    destination.unlink(missing_ok=True)
                    raise HTTPException(413, "that file is larger than 200 MB")
                handle.write(chunk)

        document = destination.with_suffix(".json")

        def work(job):
            return library.align_to_document(
                destination,
                lyrics,
                document,
                language=language,
                separate=separate,
                on_step=lambda message, progress: job.update(
                    message=message, progress=progress
                ),
            )

        job = session.jobs.start("align", destination.stem, work)
        job.extra["document"] = str(document)
        return job.as_dict()

    @app.post("/api/render")
    def start_render(request: RenderRequest) -> dict[str, Any]:
        path = current()
        song = load_song(path)
        overrides = {
            "output": {
                key: value
                for key, value in {
                    "format": request.format,
                    "width": request.width,
                    "height": request.height,
                    "fps": request.fps,
                }.items()
                if value is not None
            }
        }
        try:
            style = resolve_style(preset=request.preset, overrides=overrides)
        except ConfigError as exc:
            raise HTTPException(422, str(exc)) from exc

        from ..render import CODECS, FrameRenderer  # noqa: PLC0415
        from ..render.encode import render_segmented  # noqa: PLC0415

        if style.output.format == "png":
            raise HTTPException(422, "a PNG sequence is not something to hand back over HTTP")
        suffix = CODECS[style.output.format].suffix
        destination = path.with_name(f"{path.stem}{suffix}")
        found = audio_of(path) if style.output.audio else None

        def work(job):
            renderer = FrameRenderer(song, style)
            if not renderer.cues:
                raise ValueError("nothing to draw — every line is unsung or untimed")
            job.update(message="rendering", progress=0.0)
            render_segmented(
                renderer.frame,
                destination,
                style.output,
                start=0.0,
                end=song.audio.duration,
                audio_path=found,
                on_segment=lambda done, count: job.update(
                    message=f"segment {done} of {count}", progress=done / count
                ),
            )
            job.update(message=f"{destination.name} ready", progress=1.0)
            return destination

        job = session.jobs.start("render", destination.name, work)
        job.extra["format"] = style.output.format
        return job.as_dict()

    @app.get("/api/jobs")
    def list_jobs() -> dict[str, Any]:
        return {"jobs": [job.as_dict() for job in session.jobs.all()]}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = session.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "no such job")
        return job.as_dict()

    @app.get("/api/jobs/{job_id}/file")
    def download(job_id: str) -> Any:
        job = session.jobs.get(job_id)
        if job is None or job.result is None or not job.result.exists():
            raise HTTPException(404, "that job has produced nothing to download")
        return FileResponse(job.result, filename=job.result.name)

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
    song_path: Path | None = None,
    *,
    audio_path: Path | None = None,
    vocals_path: Path | None = None,
    workdir: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8712,
) -> None:  # pragma: no cover - starts a server
    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        create_app(song_path, audio_path, vocals_path, workdir),
        host=host,
        port=port,
        log_level="warning",
    )
