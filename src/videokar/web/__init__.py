"""The local sync view.

The friendly "you have not installed the web extra" check lives here rather than
inside the application module: FastAPI resolves handler annotations against
module globals, so the framework's own types have to be imported at the top of
that module — which means importing it at all requires FastAPI to be present.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class WebUnavailableError(RuntimeError):
    """The web extra is not installed."""


def _module():
    try:
        import fastapi  # noqa: F401, PLC0415
        import uvicorn  # noqa: F401, PLC0415
    except ImportError as exc:  # pragma: no cover - depends on install extras
        raise WebUnavailableError(
            'the web extra is not installed — pip install "videokar[web]"'
        ) from exc
    from . import app as module  # noqa: PLC0415

    return module


def create_app(
    song_path: Path | None = None,
    audio_path: Path | None = None,
    vocals_path: Path | None = None,
    workdir: Path | None = None,
) -> Any:
    """Build the FastAPI application for the sync view."""
    return _module().create_app(song_path, audio_path, vocals_path, workdir)


def serve(song_path: Path | None = None, **kwargs: Any) -> None:  # pragma: no cover
    """Run the sync view until interrupted."""
    _module().serve(song_path, **kwargs)


__all__ = ["WebUnavailableError", "create_app", "serve"]
