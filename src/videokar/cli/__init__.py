"""videokar's command line.

One module per command, all hung off the same Typer app in `root`. Imported
here in the order they should appear in `videokar --help`; each module is
imported for its side effect of registering itself.
"""

# The order of these imports is the order the commands appear in
# `videokar --help`, so it is not sorted. Each is imported for the side effect
# of registering itself on the app.
# ruff: noqa: I001, F401

from __future__ import annotations

from .root import app
from . import lyrics
from . import align
from . import check
from . import render
from . import fix
from . import serve
from . import sprite
from . import config


def main() -> None:
    app()


__all__ = ["app", "main"]


if __name__ == "__main__":  # pragma: no cover
    main()
