"""The folder of songs: what is in it, adding one, and putting one aside."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ...config import available_presets
from .. import library
from ..deps import CurrentSession
from ..models import DiscardRequest
from ..uploads import save_upload

router = APIRouter(prefix="/api")


@router.api_route("/library", methods=["GET", "HEAD"])
def get_library(session: CurrentSession) -> dict[str, Any]:
    return {
        "workdir": str(session.workdir),
        "open": str(session.song_path) if session.song_path else None,
        "songs": [entry.as_dict() for entry in library.scan(session.workdir)],
        "presets": available_presets(),
        "sprites": library.sprites(session.workdir),
        "backgrounds": library.backgrounds(session.workdir),
    }


@router.post("/discard")
def discard_song(request: DiscardRequest, session: CurrentSession) -> dict[str, Any]:
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


@router.post("/songs")
async def create_song(
    session: CurrentSession,
    audio: Annotated[UploadFile, File()],
    lyrics: Annotated[str, Form()],
    language: Annotated[str, Form()] = "en",
    separate: Annotated[bool, Form()] = True,
) -> dict[str, Any]:
    """Take an audio file and its lyrics, and align them in the background."""
    if not lyrics.strip():
        raise HTTPException(422, "the lyrics are empty")
    name = library.safe_name(audio.filename or "song")
    if Path(name).suffix.lower() not in library.AUDIO_SUFFIXES:
        raise HTTPException(422, f"{name!r} is not an audio file ffmpeg is likely to read")

    destination = await save_upload(audio, session.workdir / name)
    document = destination.with_suffix(".json")

    def work(job):
        return library.align_to_document(
            destination,
            lyrics,
            document,
            language=language,
            separate=separate,
            on_step=lambda message, progress: job.update(message=message, progress=progress),
        )

    job = session.jobs.start("align", destination.stem, work)
    job.extra["document"] = str(document)
    return job.as_dict()
