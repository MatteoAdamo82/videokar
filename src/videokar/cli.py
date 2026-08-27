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


@app.command("render")
def render_cmd(
    song_path: Annotated[Path, typer.Argument(help="Pivot JSON written by 'videokar align'.")],
    output_path: Annotated[
        Path | None, typer.Option("--out", "-o", help="Output file [SONG.mov].")
    ] = None,
    fmt: Annotated[
        str, typer.Option("--format", "-f", help="prores4444, mp4 or png.")
    ] = "prores4444",
    width: Annotated[int, typer.Option("--width")] = 1920,
    height: Annotated[int, typer.Option("--height")] = 1080,
    fps: Annotated[int, typer.Option("--fps")] = 25,
    font: Annotated[
        Path | None, typer.Option("--font", help="Font file. Defaults to a system sans.")
    ] = None,
    font_size: Annotated[
        int | None,
        typer.Option("--font-size", help="Pixels. Defaults to a size that suits --height."),
    ] = None,
    min_scale: Annotated[
        float,
        typer.Option(
            "--min-scale",
            help="Allow a too-wide line to shrink this far instead of wrapping. "
            "1.0 keeps every line the same size.",
        ),
    ] = 1.0,
    audio: Annotated[
        bool, typer.Option("--audio/--no-audio", help="Mux the original audio in.")
    ] = True,
    opaque: Annotated[
        bool,
        typer.Option("--opaque", help="Black background instead of a transparent overlay."),
    ] = False,
    segment: Annotated[
        float, typer.Option("--segment", help="Seconds per render segment.")
    ] = 60.0,
) -> None:
    """Draw the karaoke overlay and encode it."""

    from .render import CODECS, EncodeError, FrameRenderer, Output, Style, TextStyle
    from .render.encode import render_png_sequence, render_segmented
    from .render.style import FontError

    if fmt not in CODECS:
        _fail(f"unknown format {fmt!r} — one of {', '.join(sorted(CODECS))}")

    try:
        song = load_song(song_path)
    except (OSError, ProjectError) as exc:
        _fail(str(exc))

    style = Style(
        output=Output(
            width=width,
            height=height,
            fps=fps,
            format=fmt,
            background=(0, 0, 0, 255) if opaque or fmt == "mp4" else (0, 0, 0, 0),
            segment_seconds=segment,
            audio=audio,
        ),
        main=TextStyle(
            font=str(font) if font else None,
            # Tied to the frame height so the default looks the same at 720p and
            # 4K. Fixed for the whole render either way.
            size=font_size if font_size else max(12, round(height / 17)),
            min_scale=min_scale,
        ),
    )

    try:
        renderer = FrameRenderer(song, style)
    except FontError as exc:
        _fail(str(exc))

    if not renderer.cues:
        _fail("nothing to draw — every line is unsung or untimed")

    audio_file = _resolve_audio(song, song_path) if audio and fmt != "png" else None
    if audio and fmt != "png" and audio_file is None:
        console.print(f"[yellow]note:[/yellow] audio {song.audio.path!r} not found, rendering mute")

    destination = output_path or song_path.with_suffix(CODECS[fmt].suffix or "")
    end = song.audio.duration
    total_frames = int(round(end * fps))

    try:
        if fmt == "png":
            with console.status(f"rendering {total_frames} frames…", spinner="dots"):
                render_png_sequence(
                    (renderer.frame(i / fps) for i in range(total_frames)), destination
                )
        else:
            with console.status(f"rendering {total_frames} frames…", spinner="dots") as status:

                def progress(done: int, count: int) -> None:
                    status.update(f"rendering segment {done}/{count}…")

                render_segmented(
                    renderer.frame,
                    destination,
                    style.output,
                    start=0.0,
                    end=end,
                    audio_path=audio_file,
                    on_segment=progress,
                )
    except (EncodeError, OSError) as exc:
        _fail(str(exc))

    wrapped = sum(1 for cue in renderer.cues if cue.layout.rows > 1)
    console.print(
        f"[green]{total_frames}[/green] frames, {len(renderer.cues)} lines "
        f"at {width}x{height}@{fps} → {destination}"
    )
    if wrapped:
        console.print(
            f"[yellow]{wrapped}[/yellow] lines were too wide and wrapped onto two rows — "
            "use a smaller --font-size to keep them on one"
        )


def _resolve_audio(song, song_path: Path) -> Path | None:
    """Find the audio the document names, relative to the document if need be."""
    candidate = Path(song.audio.path)
    for option in (candidate, song_path.parent / candidate, song_path.parent / candidate.name):
        if option.exists():
            return option
    return None


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
