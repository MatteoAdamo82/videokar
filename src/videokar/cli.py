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

    table = Table(box=None, pad_edge=False)
    table.add_column("id", style="dim", no_wrap=True)
    table.add_column("section", style="cyan", no_wrap=True)
    table.add_column("v", no_wrap=True)
    table.add_column("line")
    table.add_column("words", justify="right", style="dim")

    for section in lyrics.sections:
        for index, line in enumerate(section.lines):
            table.add_row(
                line.id,
                (section.tag or "—") if index == 0 else "",
                "(" if line.voice == "paren" else " ",
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


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
