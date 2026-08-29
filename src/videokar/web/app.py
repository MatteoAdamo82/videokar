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

import io
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from PIL import Image
from pydantic import BaseModel

from .. import __version__
from ..audio.peaks import peaks_for
from ..config import ConfigError, available_presets, resolve_style, to_partial_toml
from ..config.loader import read_toml
from ..project import check_song, load_song, save_song
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
from ..project.io import ProjectError
from . import library
from .jobs import Jobs

logger = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"

MAX_UPLOAD = 200 * 1024 * 1024
"""Refuse anything past this rather than filling the disk with a mistake."""

SETTINGS = "videokar.toml"
"""Where the export dialog keeps its choices — the same file the CLI reads, so
what the view produces can be reproduced from a terminal."""

UNDO_DEPTH = 50
"""How many edits back you can step. Documents are small; fifty is plenty and
still nothing next to the audio already in memory."""


class RenderRequest(BaseModel):
    preset: str | None = None
    format: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    overrides: dict[str, Any] | None = None
    """Anything else from the style schema. Validated by resolve_style, so the
    page can offer a control for a setting without the server learning its name."""


class OpenRequest(BaseModel):
    path: str


class TextRequest(BaseModel):
    line: str
    text: str


class DiscardRequest(BaseModel):
    path: str
    media: bool = False


class StyleRequest(BaseModel):
    """What the export dialog wants remembered."""

    preset: str | None = None
    overrides: dict[str, Any] = {}


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

    def __init__(self, song_path: Path | None, workdir: Path) -> None:
        self.song_path = Path(song_path) if song_path else None
        self.workdir = Path(workdir)
        self.history: list[str] = []
        self.jobs = Jobs()
        self.reserved: set[str] = set()
        """Output names handed out but not yet written."""

    def require(self) -> Path:
        if self.song_path is None:
            raise FileNotFoundError("no song open — pick one, or make one from an audio file")
        return self.song_path

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

    @app.middleware("http")
    async def no_stale_answers(request, call_next):
        """Nothing here is worth caching, and a cached page is a trap.

        With no headers at all a browser caches heuristically, so an updated
        videokar serves its new page to a tab that keeps running the old one —
        which looks like the app freezing rather than like a stale cache. Every
        answer is live state; only the finished files are worth keeping.
        """
        response = await call_next(request)
        if not request.url.path.startswith(("/api/output/", "/api/audio", "/api/sprites/")):
            response.headers["Cache-Control"] = "no-store"
        return response

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
        # The version is stamped in so "are you running the current page?" has
        # an answer that does not involve guessing about the cache.
        page = (STATIC / "index.html").read_text(encoding="utf-8")
        return page.replace("{{version}}", __version__)

    @app.get("/api/song")
    def get_song() -> dict[str, Any]:
        path = current()
        session.ensure_onsets(audio_of(path))
        return _payload(load_song(path), path)

    @app.api_route("/api/library", methods=["GET", "HEAD"])
    def get_library() -> dict[str, Any]:
        return {
            "workdir": str(session.workdir),
            "open": str(session.song_path) if session.song_path else None,
            "songs": [entry.as_dict() for entry in library.scan(session.workdir)],
            "presets": available_presets(),
            "sprites": library.sprites(session.workdir),
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

    @app.get("/api/style")
    def get_style() -> dict[str, Any]:
        """The choices last saved in this folder, for the dialog to restore."""
        path = session.workdir / SETTINGS
        if not path.is_file():
            return {"path": str(path), "saved": False, "preset": None, "overrides": {}}
        try:
            data = read_toml(path)
        except ConfigError as exc:
            raise HTTPException(422, str(exc)) from exc
        preset = data.pop("preset", None)
        return {"path": str(path), "saved": True, "preset": preset, "overrides": data}

    @app.post("/api/style")
    def save_style(request: StyleRequest) -> dict[str, Any]:
        """Remember them, as a file the CLI can render from too."""
        try:
            resolve_style(preset=request.preset, overrides=request.overrides)
        except ConfigError as exc:
            raise HTTPException(422, str(exc)) from exc
        path = session.workdir / SETTINGS
        path.write_text(to_partial_toml(request.preset, request.overrides), encoding="utf-8")
        return {"path": str(path), "saved": True}

    @app.post("/api/discard")
    def discard_song(request: DiscardRequest) -> dict[str, Any]:
        """Move a song out of the folder, into .trash where it can be got back."""
        path = Path(request.path)
        try:
            moved = library.discard(path, session.workdir, media=request.media)
        except ValueError as exc:
            raise HTTPException(403, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(409, str(exc)) from exc
        if session.song_path == path:
            session.song_path = None
            session.history.clear()
        return {"moved": moved, "songs": [e.as_dict() for e in library.scan(session.workdir)]}

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

    @app.get("/api/fonts")
    def list_fonts() -> dict[str, Any]:
        from ..render.fonts import available_fonts  # noqa: PLC0415

        return {"fonts": [font.as_dict() for font in available_fonts(session.workdir)]}

    @app.post("/api/fonts")
    async def add_font(font: UploadFile = File(...)) -> dict[str, Any]:
        """Take a font file into the working folder."""
        from ..render.fonts import FONT_SUFFIXES, describe_font  # noqa: PLC0415

        name = library.safe_name(font.filename or "font.ttf")
        if Path(name).suffix.lower() not in FONT_SUFFIXES:
            raise HTTPException(422, "that is not a .ttf, .otf or .ttc")
        session.workdir.mkdir(parents=True, exist_ok=True)
        destination = session.workdir / name
        size = 0
        with open(destination, "wb") as handle:
            while chunk := await font.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    handle.close()
                    destination.unlink(missing_ok=True)
                    raise HTTPException(413, "that file is larger than 200 MB")
                handle.write(chunk)

        described = describe_font(destination)
        if described is None:
            destination.unlink(missing_ok=True)
            raise HTTPException(422, f"{name} is not a font Pillow can draw with")

        from ..render.fonts import _scan  # noqa: PLC0415

        _scan.cache_clear()
        return {
            "font": described.as_dict(),
            "fonts": [f.as_dict() for f in available_fonts_for(session)],
        }

    @app.post("/api/sprites")
    async def add_sprite(image: UploadFile = File(...)) -> dict[str, Any]:
        """Take a PNG to bounce instead of the circle."""
        name = library.safe_name(image.filename or "sprite.png")
        if Path(name).suffix.lower() not in library.SPRITE_SUFFIXES:
            raise HTTPException(422, "the bouncing thing has to be a PNG, for the transparency")
        session.workdir.mkdir(parents=True, exist_ok=True)
        destination = session.workdir / name
        size = 0
        with open(destination, "wb") as handle:
            while chunk := await image.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    handle.close()
                    destination.unlink(missing_ok=True)
                    raise HTTPException(413, "that file is larger than 200 MB")
                handle.write(chunk)

        from ..render.sprites import SpriteError, inspect_sprite  # noqa: PLC0415

        try:
            report = inspect_sprite(destination)
        except SpriteError as exc:
            destination.unlink(missing_ok=True)
            raise HTTPException(422, str(exc)) from exc
        return {
            "name": name,
            "sprites": library.sprites(session.workdir),
            # Kept rather than refused: a solid badge is a legitimate thing to
            # bounce. But it is nearly always an export that lost its alpha.
            "warnings": report.warnings,
        }

    @app.get("/api/sprites/{name}")
    def get_sprite(name: str) -> Any:
        return FileResponse(_sprite_path(session, name))

    @app.post("/api/render")
    def start_render(request: RenderRequest) -> dict[str, Any]:
        path = current()
        song = load_song(path)
        try:
            style = _style_for(request, session)
        except ConfigError as exc:
            raise HTTPException(422, str(exc)) from exc

        from ..render import CODECS, FrameRenderer  # noqa: PLC0415
        from ..render.encode import render_segmented  # noqa: PLC0415
        from ..render.visualiser import filter_chain  # noqa: PLC0415

        if style.output.format == "png":
            raise HTTPException(422, "a PNG sequence is not something to hand back over HTTP")
        suffix = CODECS[style.output.format].suffix
        destination = library.next_output(
            session.workdir, path.stem, suffix, session.reserved
        )
        session.reserved.add(destination.name)
        chain = filter_chain(style.visualiser, style.output)
        # The visualiser needs the audio even when the result is to be silent.
        found = audio_of(path) if (style.output.audio or chain) else None
        if chain and found is None:
            raise HTTPException(422, "the visualiser needs the audio, which was not found")

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
                visualiser=chain,
                on_segment=lambda done, count: job.update(
                    message=f"segment {done} of {count}", progress=done / count
                ),
            )
            job.update(message=f"{destination.name} ready", progress=1.0)
            return destination

        job = session.jobs.start("render", destination.name, work)
        job.extra["format"] = style.output.format
        job.extra["file"] = destination.name
        return job.as_dict()

    @app.get("/api/frame")
    def preview_frame(
        at: float = 0.0,
        preset: str | None = None,
        width: int = 640,
        anchor: str | None = None,
        margin_y: int | None = None,
        margin_x: int | None = None,
        paren_scale: float | None = None,
        sprite: str | None = None,
        sprite_scale: float | None = None,
        squash: float | None = None,
        font: str | None = None,
        font_size: int | None = None,
    ) -> Any:
        """One frame, small, so a setting can be judged before a render.

        Choosing where the words sit and then waiting three minutes to see it is
        not a way anyone can work.
        """
        path = current()
        song = load_song(path)
        overrides: dict[str, Any] = {"layout": {}, "paren": {}}
        if anchor is not None:
            overrides["layout"]["anchor"] = anchor
        if margin_y is not None:
            overrides["layout"]["margin_y"] = margin_y
        if margin_x is not None:
            overrides["layout"]["margin_x"] = margin_x
        if paren_scale is not None:
            overrides["paren"]["scale"] = paren_scale
        if font or font_size is not None:
            overrides["main"] = {
                **({"font": _font_path(session, font)} if font else {}),
                **({"size": font_size} if font_size is not None else {}),
            }
        if squash is not None:
            overrides["ball"] = {"squash": squash}
        if sprite:
            overrides["ball"] = {
                **overrides.get("ball", {}),
                "kind": "sprite",
                "sprite": str(_sprite_path(session, sprite)),
                **({"sprite_scale": sprite_scale} if sprite_scale is not None else {}),
            }
        try:
            style = resolve_style(preset=preset, overrides=overrides)
        except ConfigError as exc:
            raise HTTPException(422, str(exc)) from exc

        from ..render import FrameRenderer  # noqa: PLC0415
        from ..render.sprites import SpriteError  # noqa: PLC0415

        try:
            frame = FrameRenderer(song, style).frame(at)
        except SpriteError as exc:
            raise HTTPException(422, str(exc)) from exc
        # Composited onto the background it would be encoded onto, so a
        # transparent overlay is judged the way it will be seen.
        red, green, blue, _ = style.output.background
        flat = Image.new("RGB", frame.size, (red, green, blue))
        flat.paste(frame, (0, 0), frame)
        height = max(1, round(width * frame.height / frame.width))
        flat = flat.resize((width, height), Image.LANCZOS)
        buffer = io.BytesIO()
        flat.save(buffer, format="PNG")
        return Response(buffer.getvalue(), media_type="image/png")

    @app.get("/api/jobs")
    def list_jobs() -> dict[str, Any]:
        return {"jobs": [job.as_dict() for job in session.jobs.all()]}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = session.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "no such job")
        return job.as_dict()

    @app.api_route("/api/output/{name}", methods=["GET", "HEAD"])
    def download(name: str) -> Any:
        """Serve a rendered file by name, from the working directory only.

        By name rather than by job id: jobs live in memory, so a link keyed on
        one dies with the server while the file it points at is still sitting on
        disk. HEAD is answered too — a browser or a preflight asking politely
        should not get a 405 with a JSON body, which is exactly the sort of
        thing an <a download> will happily save as a file.
        """
        if name != Path(name).name:
            raise HTTPException(403, "that is not a name in this folder")
        path = session.workdir / name
        if not path.is_file():
            raise HTTPException(404, f"{name} is not there any more")
        return FileResponse(path, filename=name)

    return app


def _sprite_path(session: Session, name: str) -> Path:
    """A sprite from the working directory, and nowhere else."""
    from fastapi import HTTPException  # noqa: PLC0415

    if name != Path(name).name:
        raise HTTPException(403, "that is not a name in this folder")
    path = session.workdir / name
    if not path.is_file():
        raise HTTPException(404, f"{name} is not there")
    return path


def available_fonts_for(session: Session):
    from ..render.fonts import available_fonts  # noqa: PLC0415

    return available_fonts(session.workdir)


def _font_path(session: Session, name: str) -> str:
    """A font by path, checked to be one this machine actually offers.

    Checked rather than trusted: the page sends a path, and a path from a page
    is not a reason to read an arbitrary file off the disk.
    """
    from fastapi import HTTPException  # noqa: PLC0415

    if any(font.path == name for font in available_fonts_for(session)):
        return name
    raise HTTPException(404, f"{Path(name).name} is not a font this machine offers")


def _style_for(request: RenderRequest, session: Session | None = None):
    """The style a render request asks for, presets and overrides resolved."""
    overrides: dict[str, Any] = dict(request.overrides or {})
    main = dict(overrides.get("main") or {})
    if session is not None and main.get("font"):
        main["font"] = _font_path(session, main["font"])
        overrides["main"] = main

    ball = dict(overrides.get("ball") or {})
    if session is not None and ball.get("sprite"):
        # The page sends a bare filename; it only ever names something in the
        # folder it is working in.
        ball["sprite"] = str(_sprite_path(session, ball["sprite"]))
        ball.setdefault("kind", "sprite")
        overrides["ball"] = ball
    output = dict(overrides.get("output") or {})
    for key, value in (
        ("format", request.format),
        ("width", request.width),
        ("height", request.height),
        ("fps", request.fps),
    ):
        if value is not None:
            output[key] = value
    if output:
        overrides["output"] = output
    return resolve_style(preset=request.preset, overrides=overrides)


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
    if op == "set_line_text":
        return set_line_text(song, request.line, request.text or "")
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
