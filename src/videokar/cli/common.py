"""What every command needs: the consoles, how to fail, and how to open a song.

Kept apart from the commands so a command module is the command and nothing
else, and so `fail` reads the same wherever it is raised from.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ..project import ProjectError, load_song

console = Console()
err_console = Console(stderr=True)

SongArg = Annotated[Path, typer.Argument(help="Pivot JSON written by 'videokar align'.")]
DryRun = Annotated[bool, typer.Option("--dry-run", help="Show the result, write nothing.")]


def fail(message: str) -> None:
    err_console.print(f"[red]error:[/red] {message}")
    raise typer.Exit(1)



def open_song(song_path: Path):
    try:
        return load_song(song_path)
    except (OSError, ProjectError) as exc:
        fail(str(exc))



def resolve_audio(song, song_path: Path) -> Path | None:
    """Find the audio the document names, relative to the document if need be."""
    candidate = Path(song.audio.path)
    for option in (candidate, song_path.parent / candidate, song_path.parent / candidate.name):
        if option.exists():
            return option
    return None



def without_none(values: dict) -> dict:
    """Drop unset keys so they do not override a preset with a default."""
    return {k: v for k, v in values.items() if v is not None and v != {}}
