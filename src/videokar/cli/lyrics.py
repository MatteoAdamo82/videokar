"""`videokar lyrics` — read a lyrics file the way the aligner will read it.

Useful on its own: it says how a Suno export parses before spending minutes on
separation and alignment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from ..lyrics import ParsedLyrics, parse_lyrics_file
from ..lyrics.parser import LyricsError
from .common import console, err_console
from .root import app


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
