"""A local page for fixing sync by hand.

Every edit goes through the same operations the `fix` command uses, so the
anchor rules, the guards against inverting the timeline and the `manual` marking
behave identically whether you drag a line or type a command. The server is a
thin layer over `videokar.project.edit` and the document on disk stays the
source of truth: it is rewritten after each accepted edit, so closing the tab
never loses work and the file can be edited from the terminal in between.

This module is the assembly: the session, the headers, the page itself, and the
routers. What each route does lives in `routes/`.

Bound to localhost. It reads and writes a file on this machine and has no
authentication, so it is not something to expose.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from .routes import ROUTERS
from .session import Session

logger = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"


def create_app(
    song_path: Path | None = None,
    audio_path: Path | None = None,
    vocals_path: Path | None = None,
    workdir: Path | None = None,
):
    """Build the FastAPI application."""
    base = Path(workdir) if workdir else (Path(song_path).parent if song_path else Path.cwd())
    app = FastAPI(title="videokar", docs_url=None, redoc_url=None)
    # On the app rather than in a closure, so the routes can be their own
    # modules and still read the same state. See web/deps.py.
    app.state.session = Session(
        song_path, base, audio_path=audio_path, vocals_path=vocals_path
    )

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

    # The page's stylesheet and script, which the no-store middleware covers
    # like everything else: a cached script against an updated server is the
    # same trap as a cached page.
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        # The version is stamped in so "are you running the current page?" has
        # an answer that does not involve guessing about the cache.
        page = (STATIC / "index.html").read_text(encoding="utf-8")
        return page.replace("{{version}}", __version__)

    for router in ROUTERS:
        app.include_router(router)

    return app


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
