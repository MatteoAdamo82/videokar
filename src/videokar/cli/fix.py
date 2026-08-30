"""`videokar fix` — correcting timings by hand, one operation per command.

Every one of them rewrites the document in place, reports what moved, and says
how many lines the check is still unhappy about.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from ..project import check_song, save_song
from .common import DryRun, SongArg, console, fail, open_song
from .root import app

fix_app = typer.Typer(
    name="fix",
    help="Correct timings by hand. Every operation rewrites the JSON in place.",
    no_args_is_help=True,
)
app.add_typer(fix_app)


def _apply(song, song_path: Path, edit, dry_run: bool) -> None:
    """Report an edit, then persist it unless this is a dry run."""
    from ..project.check import ERROR as _ERROR

    console.print(f"[green]{edit.description}[/green]")
    for line_id in edit.moved:
        line = song.line(line_id)
        window = (
            f"{line.start:7.2f}-{line.end:7.2f}" if line.start is not None else "   (no timing)"
        )
        console.print(f"  [dim]{line.id:>4}[/dim] {window}  {line.words_text}")

    report = check_song(song, apply=True)
    blocking = [i for i in report.issues if i.level == _ERROR]
    for issue in blocking:
        console.print(f"[red]error[/red] [dim]{issue.line_id}[/dim] {issue.message}")

    if dry_run:
        console.print("[dim]--dry-run: nothing written[/dim]")
        return
    save_song(song, song_path)
    still = len(report.suspicious_line_ids)
    console.print(
        f"written to {song_path} — "
        f"[{'yellow' if still else 'green'}]{still}[/] lines still flagged"
    )


@fix_app.command("list")
def fix_list(
    song_path: SongArg,
    flagged: Annotated[
        bool, typer.Option("--flagged", help="Only the lines check is unhappy about.")
    ] = False,
) -> None:
    """Show line ids and timings, which is what every other operation takes."""
    song = open_song(song_path)
    table = Table(box=None, pad_edge=False)
    table.add_column("id", style="dim", no_wrap=True, min_width=4)
    table.add_column("start", justify="right", no_wrap=True, min_width=7)
    table.add_column("end", justify="right", no_wrap=True, min_width=7)
    table.add_column("", no_wrap=True, min_width=3)
    table.add_column("flags", style="yellow", no_wrap=True)
    table.add_column("line", overflow="ellipsis")
    for line in song.lines:
        if flagged and not line.flags:
            continue
        marks = ("📌" if line.pinned else " ") + ("" if line.sung else "🔇")
        window = (
            (f"{line.start:.2f}", f"{line.end:.2f}") if line.start is not None else ("—", "—")
        )
        table.add_row(line.id, window[0], window[1], marks, ",".join(line.flags), line.words_text)
    console.print(table)


@fix_app.command("shift")
def fix_shift(
    song_path: SongArg,
    line_id: Annotated[str, typer.Option("--line", "-l", help="Line id, e.g. l11.")],
    by: Annotated[
        float | None, typer.Option("--by", help="Seconds to move by, e.g. +4.3 or -0.5.")
    ] = None,
    to: Annotated[
        float | None, typer.Option("--to", help="Absolute start in seconds.")
    ] = None,
    dry_run: DryRun = False,
) -> None:
    """Move a line, carrying the lines after it up to the next pinned one."""
    from ..project.edit import FixError, set_line_start, shift_line

    if (by is None) == (to is None):
        fail("give exactly one of --by and --to")
    song = open_song(song_path)
    try:
        if by is not None:
            edit = shift_line(song, line_id, by)
        else:
            edit = set_line_start(song, line_id, to)
    except (FixError, KeyError) as exc:
        fail(str(exc))
    _apply(song, song_path, edit, dry_run)


@fix_app.command("word")
def fix_word(
    song_path: SongArg,
    word_id: Annotated[str, typer.Option("--id", "-w", help="Word id, e.g. l11.w3.")],
    by: Annotated[float | None, typer.Option("--by", help="Seconds to move by.")] = None,
    to: Annotated[float | None, typer.Option("--to", help="Absolute onset in seconds.")] = None,
    dry_run: DryRun = False,
) -> None:
    """Move a single word. Its neighbours stay where they are."""
    from ..project.edit import FixError, set_word_start, shift_word

    if (by is None) == (to is None):
        fail("give exactly one of --by and --to")
    song = open_song(song_path)
    try:
        if by is not None:
            edit = shift_word(song, word_id, by)
        else:
            edit = set_word_start(song, word_id, to)
    except (FixError, KeyError) as exc:
        fail(str(exc))
    _apply(song, song_path, edit, dry_run)


@fix_app.command("text")
def fix_text(
    song_path: SongArg,
    line_id: Annotated[str, typer.Option("--line", "-l", help="Line id, e.g. l12.")],
    text: Annotated[str, typer.Argument(help="The line as it should read.")],
    dry_run: DryRun = False,
) -> None:
    """Retype a whole line. Words that survive keep their timing."""
    from ..project.edit import FixError, set_line_text

    song = open_song(song_path)
    try:
        edit = set_line_text(song, line_id, text)
    except (FixError, KeyError) as exc:
        fail(str(exc))
    _apply(song, song_path, edit, dry_run)


@fix_app.command("stretch")
def fix_stretch(
    song_path: SongArg,
    first: Annotated[str, typer.Option("--from", "-f", help="First line id.")],
    last: Annotated[str, typer.Option("--to", "-t", help="Last line id.")],
    start: Annotated[float, typer.Option("--start", help="Where the run begins, in seconds.")],
    end: Annotated[float, typer.Option("--end", help="Where it ends, in seconds.")],
    dry_run: DryRun = False,
) -> None:
    """Fit a run of lines into an exact span, keeping their relative spacing."""
    from ..project.edit import FixError, stretch

    song = open_song(song_path)
    try:
        edit = stretch(song, first, last, start, end)
    except (FixError, KeyError) as exc:
        fail(str(exc))
    _apply(song, song_path, edit, dry_run)


@fix_app.command("pin")
def fix_pin(
    song_path: SongArg,
    line_ids: Annotated[list[str], typer.Option("--line", "-l", help="Line id. Repeatable.")],
    undo: Annotated[bool, typer.Option("--undo", help="Unpin instead.")] = False,
    dry_run: DryRun = False,
) -> None:
    """Declare a line's timing correct so a shift never moves it."""
    from ..project.edit import set_pinned

    song = open_song(song_path)
    try:
        for line_id in line_ids:
            edit = set_pinned(song, line_id, not undo)
            console.print(f"[green]{edit.description}[/green]")
    except KeyError as exc:
        fail(str(exc))
    if dry_run:
        console.print("[dim]--dry-run: nothing written[/dim]")
        return
    save_song(song, song_path)
    console.print(f"written to {song_path}")


@fix_app.command("mute")
def fix_mute(
    song_path: SongArg,
    line_id: Annotated[str, typer.Option("--line", "-l", help="Line id.")],
    undo: Annotated[bool, typer.Option("--undo", help="Mark it sung again.")] = False,
    dry_run: DryRun = False,
) -> None:
    """Take a line out of the video without deleting it from the file."""
    from ..project.edit import set_sung

    song = open_song(song_path)
    try:
        edit = set_sung(song, line_id, undo)
    except KeyError as exc:
        fail(str(exc))
    _apply(song, song_path, edit, dry_run)
