"""Fonts and sprites: what the folder offers, and taking in a new one."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import library
from ..deps import CurrentSession
from ..style import available_fonts_for, sprite_path
from ..uploads import save_upload

router = APIRouter(prefix="/api")


@router.get("/fonts")
def list_fonts(session: CurrentSession) -> dict[str, Any]:
    return {"fonts": [font.as_dict() for font in available_fonts_for(session)]}


@router.post("/fonts")
async def add_font(
    session: CurrentSession, font: Annotated[UploadFile, File()]
) -> dict[str, Any]:
    """Take a font file into the working folder."""
    from ...render.fonts import FONT_SUFFIXES, _scan, describe_font  # noqa: PLC0415

    name = library.safe_name(font.filename or "font.ttf")
    if Path(name).suffix.lower() not in FONT_SUFFIXES:
        raise HTTPException(422, "that is not a .ttf, .otf or .ttc")
    destination = await save_upload(font, session.workdir / name)

    described = describe_font(destination)
    if described is None:
        destination.unlink(missing_ok=True)
        raise HTTPException(422, f"{name} is not a font Pillow can draw with")

    _scan.cache_clear()
    return {
        "font": described.as_dict(),
        "fonts": [f.as_dict() for f in available_fonts_for(session)],
    }


@router.post("/sprites")
async def add_sprite(
    session: CurrentSession, image: Annotated[UploadFile, File()]
) -> dict[str, Any]:
    """Take a PNG to bounce instead of the circle."""
    from ...render.sprites import SpriteError, inspect_sprite  # noqa: PLC0415

    name = library.safe_name(image.filename or "sprite.png")
    if Path(name).suffix.lower() not in library.SPRITE_SUFFIXES:
        raise HTTPException(422, "the bouncing thing has to be a PNG, for the transparency")
    destination = await save_upload(image, session.workdir / name)

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


@router.get("/sprites/{name}")
def get_sprite(name: str, session: CurrentSession) -> Any:
    return FileResponse(sprite_path(session, name))
