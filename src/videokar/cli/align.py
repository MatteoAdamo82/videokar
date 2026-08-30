"""`videokar align` — time the lyrics against the audio and write the document."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ..lyrics import parse_lyrics_file
from ..lyrics.parser import LyricsError
from ..project import build_song, save_song
from .common import console, fail
from .root import app


@app.command("align")
def align_cmd(
    audio: Annotated[Path, typer.Argument(help="Audio file: mp3, wav, aif, m4a, flac.")],
    lyrics_path: Annotated[
        Path | None, typer.Option("--lyrics", "-l", help="Lyrics file. Required for now.")
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--out", "-o", help="Where to write the JSON [AUDIO.json].")
    ] = None,
    language: Annotated[str, typer.Option("--lang", help="Language of the lyrics.")] = "en",
    device: Annotated[
        str, typer.Option("--device", help="auto, cpu, mps or cuda.")
    ] = "auto",
    separator: Annotated[
        str, typer.Option("--separator", help="demucs model used to isolate the vocal.")
    ] = "htdemucs",
    separate: Annotated[
        bool,
        typer.Option(
            "--separate/--no-separate",
            help="Isolate the vocal first. Turning this off is faster and clearly worse.",
        ),
    ] = True,
    use_cache: Annotated[
        bool, typer.Option("--cache/--no-cache", help="Reuse a cached vocal stem.")
    ] = True,
) -> None:
    """Time the lyrics against the audio and write the pivot JSON."""
    if lyrics_path is None:
        fail(
            "no lyrics given — pass --lyrics FILE. "
            "Generating them from the audio is not implemented yet."
        )

    try:
        lyrics = parse_lyrics_file(lyrics_path, language=language)
    except (OSError, LyricsError) as exc:
        fail(str(exc))

    from ..pipeline import run_alignment

    destination = output or audio.with_suffix(".json")
    with console.status(f"aligning {len(lyrics.alignable_words)} words…", spinner="dots"):
        try:
            track = run_alignment(
                audio,
                lyrics,
                separate=separate,
                separation_model=separator,
                device=device,
                use_cache=use_cache,
            )
        except (OSError, RuntimeError) as exc:
            fail(str(exc))

    song = build_song(track, audio_path=audio)
    save_song(song, destination)

    flagged = [line for line in song.lines if line.flags]
    console.print(
        f"[green]{len(song.words)}[/green] words over [green]{len(song.lines)}[/green] lines "
        f"in {track.elapsed:.1f}s on {track.alignment.device} → {destination}"
    )
    if flagged:
        console.print(
            f"[yellow]{len(flagged)}[/yellow] lines look wrong — "
            f"run [bold]videokar check {destination}[/bold]"
        )
