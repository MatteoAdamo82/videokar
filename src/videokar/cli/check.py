"""`videokar check` — which lines are worth a second look, and why."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from ..project import check_song, save_song
from ..project.check import ERROR
from .common import console, open_song, resolve_audio
from .root import app


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
    song = open_song(song_path)

    # A document written before onsets existed can still be measured against
    # them, rather than having to be aligned again for a check.
    if not song.vocal_onsets:
        audio_file = resolve_audio(song, song_path)
        if audio_file is not None:
            from ..pipeline import onsets_for

            with console.status("finding the vocal attacks…", spinner="dots"):
                song.vocal_onsets = onsets_for(audio_file)
            write = True

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
    table.add_column("off", justify="right", no_wrap=True, min_width=6)
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
            "—" if line_report.onset_distance is None else f"{line_report.onset_distance:+.2f}",
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
