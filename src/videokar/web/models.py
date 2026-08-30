"""What the page sends, as the shapes FastAPI validates it into.

Declared at module level on purpose: postponed annotations turn a handler
signature into a string, and FastAPI resolves it against the module's globals.
A model defined inside a factory is invisible from there, and every request
comes back as a validation error.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


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

