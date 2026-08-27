"""videokar command line entry point.

Commands are added one pipeline stage at a time; `lyrics` is the inspection
command for the parser, useful on its own to check how a Suno export will be
read before spending minutes on separation and alignment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .lyrics import ParsedLyrics, parse_lyrics_file
from .lyrics.parser import LyricsError
from .project import ProjectError, build_song, check_song, load_song, save_song
from .project.check import ERROR

app = typer.Typer(
    name="videokar",
    help="Bouncing-ball karaoke lyric videos from an audio track and its lyrics.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


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


def _as_dict(lyrics: ParsedLyrics) -> dict:
    return {
        "language": lyrics.language,
        "sections": [
            {
                "id": section.id,
                "tag": section.tag,
                "lines": [
                    {
                        "id": line.id,
                        "text": line.text,
                        "voice": line.voice,
                        "direction": line.direction,
                        "source_line": line.source_line,
                        "tokens": [{"text": t.text, "norm": t.norm} for t in line.tokens],
                    }
                    for line in section.lines
                ],
            }
            for section in lyrics.sections
        ],
    }


@app.command("lyrics")
def lyrics_cmd(
    path: Annotated[Path, typer.Argument(help="Lyrics file (.txt), Suno tags allowed.")],
    language: Annotated[str, typer.Option("--lang", help="Language of the lyrics.")] = "en",
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the parse result as JSON instead of a table.")
    ] = False,
) -> None:
    """Parse a lyrics file and show how it will be fed to the aligner."""
    try:
        lyrics = parse_lyrics_file(path, language=language)
    except (OSError, LyricsError) as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1) from exc

    if as_json:
        console.print_json(json.dumps(_as_dict(lyrics)))
        return

    table = Table(box=None, pad_edge=False, show_header=False)
    table.add_column("id", style="dim", no_wrap=True)
    table.add_column("voice", no_wrap=True)
    table.add_column("line", no_wrap=True)
    table.add_column("words", justify="right", style="dim", no_wrap=True)

    for section in lyrics.sections:
        label = f"[{section.tag}]" if section.tag else "[untagged]"
        empty = "" if section.lines else "  [dim](no lines)[/dim]"
        table.add_row("", "", f"[cyan]{label}[/cyan]{empty}", "")
        direction = None
        for line in section.lines:
            if line.direction != direction:
                direction = line.direction
                if direction:
                    table.add_row("", "", f"  [magenta]↳ {direction}[/magenta]", "")
            table.add_row(
                line.id,
                "[dim]([/dim]" if line.voice == "paren" else " ",
                line.text,
                str(len(line.alignable_tokens)),
            )

    console.print(table)
    unalignable = [t.text for _, t in lyrics.iter_tokens() if not t.alignable]
    console.print(
        f"\n[bold]{len(lyrics.sections)}[/bold] sections, "
        f"[bold]{len(lyrics)}[/bold] lines, "
        f"[bold]{len(lyrics.alignable_words)}[/bold] alignable words"
    )
    if unalignable:
        console.print(f"[yellow]{len(unalignable)}[/yellow] tokens carry no timing: {unalignable}")




def _fail(message: str) -> None:
    err_console.print(f"[red]error:[/red] {message}")
    raise typer.Exit(1)


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
        _fail(
            "no lyrics given — pass --lyrics FILE. "
            "Generating them from the audio is not implemented yet."
        )

    try:
        lyrics = parse_lyrics_file(lyrics_path, language=language)
    except (OSError, LyricsError) as exc:
        _fail(str(exc))

    from .pipeline import run_alignment

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
            _fail(str(exc))

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


@app.command("check")
def check_cmd(
    song_path: Annotated[Path, typer.Argument(help="Pivot JSON written by 'videokar align'.")],
    show_all: Annotated[
        bool, typer.Option("--all", help="List every line, not only the suspicious ones.")
    ] = False,
    write: Annotated[
        bool, typer.Option("--write", help="Save the recomputed flags back into the file.")
    ] = False,
) -> None:
    """Report which lines are worth a second look, and any hand-editing damage."""
    try:
        song = load_song(song_path)
    except (OSError, ProjectError) as exc:
        _fail(str(exc))

    report = check_song(song, apply=True)
    lines = {line.id: line for line in song.lines}

    # Fixed widths on the numbers: left to itself rich squeezes the id column
    # down to an ellipsis, and an id you cannot read is no use to 'fix'.
    table = Table(box=None, pad_edge=False)
    table.add_column("id", style="dim", no_wrap=True, min_width=4)
    table.add_column("start", justify="right", no_wrap=True, min_width=7)
    table.add_column("end", justify="right", no_wrap=True, min_width=7)
    table.add_column("w/s", justify="right", no_wrap=True, min_width=4)
    table.add_column("score", justify="right", no_wrap=True, min_width=5)
    table.add_column("flags", style="yellow", no_wrap=True, min_width=17)
    table.add_column("line", overflow="ellipsis")

    shown = 0
    for line_report in report.reports:
        if not show_all and not line_report.suspicious:
            continue
        shown += 1
        line = lines[report.line_ids[line_report.index]]
        table.add_row(
            line.id,
            f"{line_report.start:.2f}",
            f"{line_report.end:.2f}",
            f"{line_report.rate:.1f}",
            f"{line_report.score:.2f}",
            ",".join(line_report.flags),
            line.words_text,
        )
    if shown:
        console.print(table)

    for issue in report.issues:
        colour = "red" if issue.level == ERROR else "yellow"
        where = f"[dim]{issue.line_id}[/dim] " if issue.line_id else ""
        console.print(f"[{colour}]{issue.level}[/{colour}] {where}{issue.message}")

    suspicious = len(report.suspicious_line_ids)
    console.print(
        f"\n[bold]{len(song.lines)}[/bold] lines, "
        f"[{'yellow' if suspicious else 'green'}]{suspicious}[/] suspicious, "
        f"[{'red' if report.errors else 'green'}]{len(report.errors)}[/] errors"
    )

    if write:
        save_song(song, song_path)
        console.print(f"flags written to {song_path}")

    if report.errors:
        raise typer.Exit(1)


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
