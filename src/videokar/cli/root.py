"""The top-level command, and the version behind --version.

Its own module because every command module imports `app` to hang itself off,
and a command importing the package would be a cycle.
"""

from __future__ import annotations

from typing import Annotated

import typer

from .. import __version__
from .common import console

app = typer.Typer(
    name="videokar",
    help="Bouncing-ball karaoke lyric videos from an audio track and its lyrics.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"videokar {__version__}")
        raise typer.Exit


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    pass
