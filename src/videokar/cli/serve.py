"""`videokar serve` — the sync view."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .common import console, fail, open_song, resolve_audio
from .root import app


@app.command("serve")
def serve_cmd(
    song_path: Annotated[
        Path | None,
        typer.Argument(help="Pivot JSON to open. Omit to start on the library."),
    ] = None,
    workdir: Annotated[
        Path | None,
        typer.Option("--dir", "-d", help="Folder the view lists and writes into."),
    ] = None,
    port: Annotated[int, typer.Option("--port", "-p")] = 8712,
    host: Annotated[
        str, typer.Option("--host", help="Leave this alone unless you know why.")
    ] = "127.0.0.1",
    separate: Annotated[
        bool,
        typer.Option(
            "--separate/--no-separate",
            help="Draw the waveform from the isolated vocal rather than the mix.",
        ),
    ] = True,
) -> None:
    """Open the sync view: pick a song, fix the timings, export the video."""
    from ..web import WebUnavailableError, serve

    audio_file = None
    vocals = None
    if song_path is not None:
        song = open_song(song_path)
        audio_file = resolve_audio(song, song_path)
        if audio_file is None:
            console.print(
                f"[yellow]note:[/yellow] audio {song.audio.path!r} not found — "
                "no waveform and no playback"
            )
        elif separate:
            from ..audio.separate import SeparationError, separate_vocals

            try:
                with console.status("isolating the vocal for the waveform…", spinner="dots"):
                    vocals = separate_vocals(audio_file).vocals_path
            except SeparationError as exc:
                console.print(f"[yellow]note:[/yellow] {exc} — drawing the full mix instead")

    base = workdir or (song_path.parent if song_path else Path.cwd())
    console.print(f"sync view on [bold]http://{host}:{port}[/bold] — folder {base}")
    console.print("[dim]edits are written straight to the file; ctrl-c to stop[/dim]")
    try:
        serve(
            song_path,
            audio_path=audio_file,
            vocals_path=vocals,
            workdir=base,
            host=host,
            port=port,
        )
    except WebUnavailableError as exc:
        fail(str(exc))
