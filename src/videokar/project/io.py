"""Reading and writing the pivot document."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from .model import SCHEMA_VERSION, Song


class ProjectError(RuntimeError):
    """The JSON on disk is not a videokar document this version understands."""


def load_song(path: str | Path) -> Song:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectError(f"{path} is not valid JSON: {exc}") from exc

    version = payload.get("schema")
    if version is not None and version > SCHEMA_VERSION:
        raise ProjectError(
            f"{path} uses schema {version}, this videokar understands {SCHEMA_VERSION} — upgrade"
        )
    try:
        return Song.model_validate(payload)
    except ValidationError as exc:
        raise ProjectError(f"{path} is not a videokar document:\n{exc}") from exc


def dumps(song: Song) -> str:
    """Serialise the document the way it is meant to be read.

    Structure is indented, but a word and a vocal region each stay on one line.
    Fully expanded, two hundred words become sixteen hundred lines of JSON to
    scroll through and a one-word correction becomes an eight-line diff; on one
    line each, a word is a row you can scan and edit in place.
    """
    payload = song.model_dump(by_alias=True, exclude_none=False)
    inline: dict[str, str] = {}

    def hold(value: object) -> str:
        key = f"\x00{len(inline)}\x00"
        inline[key] = json.dumps(value, ensure_ascii=False)
        return key

    payload["vocal_regions"] = [hold(region) for region in payload["vocal_regions"]]
    for section in payload["sections"]:
        for line in section["lines"]:
            line["words"] = [hold(word) for word in line["words"]]

    text = json.dumps(payload, indent=1, ensure_ascii=False)
    for key, value in inline.items():
        text = text.replace(json.dumps(key), value)
    return text + "\n"


def save_song(song: Song, path: str | Path) -> Path:
    """Write the document, formatted for reading and for a useful diff."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(song), encoding="utf-8")
    return path
