"""Turning what the page asked for into a resolved style.

A path from a page is not a reason to read a file: a font has to be one this
machine actually offers, and a sprite has to be a name in the working folder.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..config import resolve_style
from .models import RenderRequest
from .session import Session


def sprite_path(session: Session, name: str) -> Path:
    """A sprite from the working directory, and nowhere else."""
    if name != Path(name).name:
        raise HTTPException(403, "that is not a name in this folder")
    path = session.workdir / name
    if not path.is_file():
        raise HTTPException(404, f"{name} is not there")
    return path



def available_fonts_for(session: Session):
    from ..render.fonts import available_fonts  # noqa: PLC0415

    return available_fonts(session.workdir)



def font_path(session: Session, name: str) -> str:
    """A font by path, checked to be one this machine actually offers.

    Checked rather than trusted: the page sends a path, and a path from a page
    is not a reason to read an arbitrary file off the disk.
    """
    if any(font.path == name for font in available_fonts_for(session)):
        return name
    raise HTTPException(404, f"{Path(name).name} is not a font this machine offers")



def style_for(request: RenderRequest, session: Session | None = None):
    """The style a render request asks for, presets and overrides resolved."""
    overrides: dict[str, Any] = dict(request.overrides or {})
    main = dict(overrides.get("main") or {})
    if session is not None and main.get("font"):
        main["font"] = font_path(session, main["font"])
        overrides["main"] = main

    ball = dict(overrides.get("ball") or {})
    if session is not None and ball.get("sprite"):
        # The page sends a bare filename; it only ever names something in the
        # folder it is working in.
        ball["sprite"] = str(sprite_path(session, ball["sprite"]))
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
