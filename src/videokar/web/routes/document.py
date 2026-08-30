"""The open document: reading it, switching to another, and changing it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ...audio.peaks import peaks_for
from ...project import load_song, save_song
from ...project.edit import FixError
from ...project.io import ProjectError
from ..deps import CurrentSession
from ..edits import dispatch
from ..models import EditRequest, OpenRequest
from ..session import UNDO_DEPTH, payload

router = APIRouter(prefix="/api")


@router.get("/song")
def get_song(session: CurrentSession) -> dict[str, Any]:
    path = session.current()
    session.ensure_onsets(session.audio_of(path))
    return payload(load_song(path), path)


@router.post("/open")
def open_song(request: OpenRequest, session: CurrentSession) -> dict[str, Any]:
    path = Path(request.path)
    if path.parent.resolve() != session.workdir.resolve():
        raise HTTPException(403, "that file is outside the working directory")
    try:
        session.open(path)
    except (OSError, ProjectError) as exc:
        raise HTTPException(409, str(exc)) from exc
    return payload(load_song(path), path)


@router.get("/peaks")
def get_peaks(session: CurrentSession) -> dict[str, Any]:
    found = session.audio_of(session.current())
    if found is None:
        raise HTTPException(404, "the audio this document names could not be found")
    return peaks_for(found, vocals_path=session.vocals_of(found))


@router.get("/audio")
def get_audio(session: CurrentSession) -> Any:
    found = session.audio_of(session.current())
    if found is None:
        raise HTTPException(404, "the audio this document names could not be found")
    return FileResponse(found)


@router.post("/edit")
def apply_edit(request: EditRequest, session: CurrentSession) -> dict[str, Any]:
    path = session.current()
    before = path.read_text(encoding="utf-8")
    song = load_song(path)
    try:
        edit = dispatch(song, request)
    except (FixError, KeyError) as exc:
        # A refused edit is the normal way to learn a drag was impossible, so it
        # comes back as a message for the page rather than a 500. One status for
        # every refusal, including an id that does not exist: the page shows the
        # reason either way, and the operations disagree about which exception an
        # unknown id raises. KeyError stringifies its argument with repr, so only
        # that one needs unwrapping.
        detail = exc.args[0] if isinstance(exc, KeyError) else str(exc)
        raise HTTPException(409, str(detail)) from exc

    session.history.append(before)
    del session.history[:-UNDO_DEPTH]
    save_song(song, path)
    result = payload(song, path)
    result["edit"] = {"description": edit.description, "moved": edit.moved}
    result["undo_depth"] = len(session.history)
    return result


@router.post("/undo")
def undo(session: CurrentSession) -> dict[str, Any]:
    path = session.current()
    if not session.history:
        raise HTTPException(409, "nothing to undo")
    path.write_text(session.history.pop(), encoding="utf-8")
    result = payload(load_song(path), path)
    result["edit"] = {"description": "undone", "moved": []}
    result["undo_depth"] = len(session.history)
    return result
