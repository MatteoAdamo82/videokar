"""The routes, one module per area of the page.

Every handler takes the session as a dependency rather than closing over it,
so they can live out here and still be reading the same state.
"""

from __future__ import annotations

from . import assets, document, jobs, songs, video

ROUTERS = [document.router, songs.router, assets.router, video.router, jobs.router]

__all__ = ["ROUTERS"]
