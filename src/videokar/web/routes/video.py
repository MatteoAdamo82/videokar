"""Making the video: what the dialog remembers, a still to judge it by, the
render itself, and handing the finished file back."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from PIL import Image

from ...config import ConfigError, resolve_style, to_partial_toml
from ...config.loader import read_toml
from ...project import load_song
from ...render.background import CLIP_SUFFIXES
from .. import library
from ..deps import CurrentSession
from ..models import RenderRequest, StyleRequest
from ..preview import still_for
from ..session import SETTINGS
from ..style import background_path, font_path, named_background, sprite_path, style_for

router = APIRouter(prefix="/api")


def _spectrum_for(session, path, style):
    """The analysis the meter needs, or nothing when it is switched off.

    Cached beside the audio, so only the first frame drawn for a song pays for
    it and every slider after that is instant.
    """
    if style.meter.kind == "none":
        return None
    found = session.audio_of(path)
    if found is None:
        raise HTTPException(
            422, "the meter needs the audio, and the file this document names is not there"
        )
    from ...audio.spectrum import spectrum_for  # noqa: PLC0415

    return spectrum_for(found, fps=float(style.output.rate), bands=style.meter.bands)


@router.get("/style")
def get_style(session: CurrentSession) -> dict[str, Any]:
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


@router.post("/style")
def save_style(request: StyleRequest, session: CurrentSession) -> dict[str, Any]:
    """Remember them, as a file the CLI can render from too."""
    # The name the page sends becomes the path the schema wants, here as well as
    # on the way to a render: this file is the one `videokar render -c` reads,
    # and a key the schema has never heard of would be dropped in silence.
    overrides = named_background(session, request.overrides)
    try:
        resolve_style(preset=request.preset, overrides=overrides)
    except ConfigError as exc:
        raise HTTPException(422, str(exc)) from exc
    path = session.workdir / SETTINGS
    path.write_text(to_partial_toml(request.preset, overrides), encoding="utf-8")
    return {"path": str(path), "saved": True}


@router.post("/render")
def start_render(request: RenderRequest, session: CurrentSession) -> dict[str, Any]:
    path = session.current()
    song = load_song(path)
    try:
        style = style_for(request, session)
    except ConfigError as exc:
        raise HTTPException(422, str(exc)) from exc

    from ...render import CODECS, FrameRenderer  # noqa: PLC0415
    from ...render.encode import render_segmented  # noqa: PLC0415

    if style.output.format == "png":
        raise HTTPException(422, "a PNG sequence is not something to hand back over HTTP")
    suffix = CODECS[style.output.format].suffix
    destination = library.next_output(
        session.workdir, path.stem, suffix, session.reserved
    )
    session.reserved.add(destination.name)
    found = session.audio_of(path) if style.output.audio else None

    # Analysed before the job starts, so a missing audio file is a refusal the
    # dialog can show rather than a job that fails a minute later.
    spectrum = _spectrum_for(session, path, style)

    def work(job):
        renderer = FrameRenderer(song, style, spectrum=spectrum)
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
            background=style.background,
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


@router.get("/frame")
def preview_frame(
    session: CurrentSession,
    at: float = 0.0,
    preset: str | None = None,
    width: int = 640,
    anchor: str | None = None,
    margin_y: int | None = None,
    margin_x: int | None = None,
    paren_scale: float | None = None,
    sprite: str | None = None,
    sprite_scale: float | None = None,
    behind: str | None = None,
    squash: float | None = None,
    font: str | None = None,
    font_size: int | None = None,
    extra: str | None = None,
) -> Any:
    """One frame, small, so a setting can be judged before a render.

    Choosing where the words sit and then waiting three minutes to see it is
    not a way anyone can work.
    """
    path = session.current()
    song = load_song(path)
    overrides: dict[str, Any] = {"layout": {}, "paren": {}}
    if extra:
        # The same shape the render takes, merged in first, so a new control
        # on the page does not mean another parameter here every time.
        try:
            more = json.loads(extra)
        except json.JSONDecodeError as exc:
            raise HTTPException(422, f"extra is not JSON: {exc}") from exc
        if not isinstance(more, dict):
            raise HTTPException(422, "extra must be an object")
        for section, values in more.items():
            overrides[section] = {**overrides.get(section, {}), **(values or {})}
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
            **({"font": font_path(session, font)} if font else {}),
            **({"size": font_size} if font_size is not None else {}),
        }
    # Merged, never replaced: `extra` carries the ball's colour and radius, and
    # a named parameter that assigns over the section would drop them.
    if squash is not None:
        overrides["ball"] = {**overrides.get("ball", {}), "squash": squash}
    if behind:
        path = Path(background_path(session, behind))
        if path.suffix.lower() in CLIP_SUFFIXES:
            # A clip is composited by ffmpeg when encoding, which has not
            # happened yet — so one frame of it stands in for the whole thing.
            overrides["background"] = {
                **overrides.get("background", {}),
                "image": still_for(path, at),
            }
        else:
            overrides["background"] = {**overrides.get("background", {}), "image": str(path)}
    if sprite:
        overrides["ball"] = {
            **overrides.get("ball", {}),
            "kind": "sprite",
            "sprite": str(sprite_path(session, sprite)),
            **({"sprite_scale": sprite_scale} if sprite_scale is not None else {}),
        }
    try:
        style = resolve_style(preset=preset, overrides=overrides)
    except ConfigError as exc:
        raise HTTPException(422, str(exc)) from exc

    from ...render import FrameRenderer  # noqa: PLC0415
    from ...render.background import BackgroundError  # noqa: PLC0415
    from ...render.sprites import SpriteError  # noqa: PLC0415

    try:
        frame = FrameRenderer(song, style, spectrum=_spectrum_for(session, path, style)).frame(at)
    except (SpriteError, BackgroundError) as exc:
        # A background on a transparent preset is the common one, and the
        # message says which presets do take one.
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


@router.api_route("/output/{name}", methods=["GET", "HEAD"])
def download(name: str, session: CurrentSession) -> Any:
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
