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
from .config.loader import PRESETS as PRESETS_DIR
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
        Path | None, typer.Option("--out", "-o", help="Output file [SONG + format suffix].")
    ] = None,
    config_path: Annotated[
        Path | None, typer.Option("--config", "-c", help="TOML written by 'videokar config init'.")
    ] = None,
    preset: Annotated[
        str | None, typer.Option("--preset", help="Built-in preset to build on.")
    ] = None,
    fmt: Annotated[
        str | None, typer.Option("--format", "-f", help="prores4444, mp4 or png.")
    ] = None,
    width: Annotated[int | None, typer.Option("--width")] = None,
    height: Annotated[int | None, typer.Option("--height")] = None,
    fps: Annotated[
        float | None,
        typer.Option("--fps", help="Match your editing timeline. 23.976 and 29.97 work."),
    ] = None,
    font: Annotated[Path | None, typer.Option("--font", help="Font file.")] = None,
    font_size: Annotated[
        int | None, typer.Option("--font-size", help="Pixels. Default follows --height.")
    ] = None,
    min_scale: Annotated[
        float | None,
        typer.Option("--min-scale", help="Let a too-wide line shrink this far before wrapping."),
    ] = None,
    sprite: Annotated[
        Path | None,
        typer.Option("--sprite", help="PNG with alpha to bounce instead of the circle."),
    ] = None,
    sprite_scale: Annotated[
        float | None, typer.Option("--sprite-scale", help="Size relative to the circle.")
    ] = None,
    audio: Annotated[
        bool | None, typer.Option("--audio/--no-audio", help="Mux the original audio in.")
    ] = None,
    opaque: Annotated[
        bool, typer.Option("--opaque", help="Black background instead of a transparent overlay.")
    ] = False,
    segment: Annotated[
        float | None, typer.Option("--segment", help="Seconds per render segment.")
    ] = None,
) -> None:
    """Draw the karaoke overlay and encode it."""
    from .config import ConfigError, resolve_style
    from .render import CODECS, EncodeError, FontError, FrameRenderer
    from .render.encode import render_png_sequence, render_segmented
    from .render.sprites import SpriteError

    # Command-line flags are the last layer over presets and the file, so an
    # unset flag has to be absent rather than a default that silently wins.
    overrides = {
        "output": _without_none(
            {
                "format": fmt,
                "width": width,
                "height": height,
                "fps": fps,
                "audio": audio,
                "segment_seconds": segment,
                "background": "#000000ff" if opaque else None,
            }
        ),
        "main": _without_none(
            {"font": str(font) if font else None, "size": font_size, "min_scale": min_scale}
        ),
        "ball": _without_none(
            {
                "kind": "sprite" if sprite else None,
                "sprite": str(sprite) if sprite else None,
                "sprite_scale": sprite_scale,
            }
        ),
    }

    try:
        style = resolve_style(config_path, preset=preset, overrides=_without_none(overrides))
    except ConfigError as exc:
        _fail(str(exc))

    if style.output.format not in CODECS:
        _fail(f"unknown format {style.output.format!r} — one of {', '.join(sorted(CODECS))}")
    if style.output.format == "mp4" and style.output.background[3] < 255:
        # H.264 has no alpha, so a transparent background would silently become
        # black. Say so rather than surprising anyone with it.
        console.print("[yellow]note:[/yellow] mp4 has no alpha — compositing onto black")
        style = _with_opaque_background(style)

    try:
        song = load_song(song_path)
    except (OSError, ProjectError) as exc:
        _fail(str(exc))

    try:
        renderer = FrameRenderer(song, style)
    except (FontError, SpriteError) as exc:
        _fail(str(exc))
    if not renderer.cues:
        _fail("nothing to draw — every line is unsung or untimed")

    output = style.output
    audio_file = (
        _resolve_audio(song, song_path) if output.audio and output.format != "png" else None
    )
    if output.audio and output.format != "png" and audio_file is None:
        console.print(f"[yellow]note:[/yellow] audio {song.audio.path!r} not found, rendering mute")

    suffix = CODECS[output.format].suffix
    destination = output_path or song_path.with_suffix(suffix or "")
    total_frames = output.frame_count(song.audio.duration)

    try:
        if output.format == "png":
            with console.status(f"rendering {total_frames} frames…", spinner="dots"):
                render_png_sequence(
                    (renderer.frame(output.frame_time(i)) for i in range(total_frames)),
                    destination,
                )
        else:
            with console.status(f"rendering {total_frames} frames…", spinner="dots") as status:

                def progress(done: int, count: int) -> None:
                    status.update(f"rendering segment {done}/{count}…")

                render_segmented(
                    renderer.frame,
                    destination,
                    output,
                    start=0.0,
                    end=song.audio.duration,
                    audio_path=audio_file,
                    on_segment=progress,
                )
    except (EncodeError, OSError) as exc:
        _fail(str(exc))

    wrapped = sum(1 for cue in renderer.cues if cue.layout.rows > 1)
    console.print(
        f"[green]{total_frames}[/green] frames, {len(renderer.cues)} lines "
        f"at {output.width}x{output.height}@{output.fps} → {destination}"
    )
    if wrapped:
        console.print(
            f"[yellow]{wrapped}[/yellow] lines were too wide and wrapped onto two rows — "
            "use a smaller font size to keep them on one"
        )


def _without_none(values: dict) -> dict:
    """Drop unset keys so they do not override a preset with a default."""
    return {k: v for k, v in values.items() if v is not None and v != {}}


def _with_opaque_background(style):
    from dataclasses import replace

    red, green, blue, _ = style.output.background
    return replace(style, output=replace(style.output, background=(red, green, blue, 255)))


def _resolve_audio(song, song_path: Path) -> Path | None:
    """Find the audio the document names, relative to the document if need be."""
    candidate = Path(song.audio.path)
    for option in (candidate, song_path.parent / candidate, song_path.parent / candidate.name):
        if option.exists():
            return option
    return None


fix_app = typer.Typer(
    name="fix",
    help="Correct timings by hand. Every operation rewrites the JSON in place.",
    no_args_is_help=True,
)
app.add_typer(fix_app)

SongArg = Annotated[Path, typer.Argument(help="Pivot JSON written by 'videokar align'.")]
DryRun = Annotated[bool, typer.Option("--dry-run", help="Show the result, write nothing.")]


def _open(song_path: Path):
    try:
        return load_song(song_path)
    except (OSError, ProjectError) as exc:
        _fail(str(exc))


def _apply(song, song_path: Path, edit, dry_run: bool) -> None:
    """Report an edit, then persist it unless this is a dry run."""
    from .project.check import ERROR as _ERROR

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
    song = _open(song_path)
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
    from .project.edit import FixError, set_line_start, shift_line

    if (by is None) == (to is None):
        _fail("give exactly one of --by and --to")
    song = _open(song_path)
    try:
        if by is not None:
            edit = shift_line(song, line_id, by)
        else:
            edit = set_line_start(song, line_id, to)
    except (FixError, KeyError) as exc:
        _fail(str(exc))
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
    from .project.edit import FixError, set_word_start, shift_word

    if (by is None) == (to is None):
        _fail("give exactly one of --by and --to")
    song = _open(song_path)
    try:
        if by is not None:
            edit = shift_word(song, word_id, by)
        else:
            edit = set_word_start(song, word_id, to)
    except (FixError, KeyError) as exc:
        _fail(str(exc))
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
    from .project.edit import FixError, stretch

    song = _open(song_path)
    try:
        edit = stretch(song, first, last, start, end)
    except (FixError, KeyError) as exc:
        _fail(str(exc))
    _apply(song, song_path, edit, dry_run)


@fix_app.command("pin")
def fix_pin(
    song_path: SongArg,
    line_ids: Annotated[list[str], typer.Option("--line", "-l", help="Line id. Repeatable.")],
    undo: Annotated[bool, typer.Option("--undo", help="Unpin instead.")] = False,
    dry_run: DryRun = False,
) -> None:
    """Declare a line's timing correct so a shift never moves it."""
    from .project.edit import set_pinned

    song = _open(song_path)
    try:
        for line_id in line_ids:
            edit = set_pinned(song, line_id, not undo)
            console.print(f"[green]{edit.description}[/green]")
    except KeyError as exc:
        _fail(str(exc))
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
    from .project.edit import set_sung

    song = _open(song_path)
    try:
        edit = set_sung(song, line_id, undo)
    except KeyError as exc:
        _fail(str(exc))
    _apply(song, song_path, edit, dry_run)


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
    from .web import WebUnavailableError, serve

    audio_file = None
    vocals = None
    if song_path is not None:
        song = _open(song_path)
        audio_file = _resolve_audio(song, song_path)
        if audio_file is None:
            console.print(
                f"[yellow]note:[/yellow] audio {song.audio.path!r} not found — "
                "no waveform and no playback"
            )
        elif separate:
            from .audio.separate import SeparationError, separate_vocals

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
        _fail(str(exc))


config_app = typer.Typer(
    name="config", help="The look of the video: presets and the file that overrides them.",
    no_args_is_help=True,
)
app.add_typer(config_app)


@config_app.command("presets")
def config_presets() -> None:
    """List the built-in presets."""
    from .config import available_presets, resolve_style

    table = Table(box=None, pad_edge=False)
    table.add_column("preset", style="cyan", no_wrap=True)
    table.add_column("size", no_wrap=True)
    table.add_column("format", no_wrap=True)
    table.add_column("what it is for", overflow="fold")
    for name in available_presets():
        style = resolve_style(preset=name)
        blurb = (PRESETS_DIR / f"{name}.toml").read_text(encoding="utf-8").splitlines()[0]
        table.add_row(
            name,
            f"{style.output.width}x{style.output.height}@{style.output.fps}",
            style.output.format,
            blurb.lstrip("# ").rstrip(),
        )
    console.print(table)


@config_app.command("init")
def config_init(
    output_path: Annotated[
        Path, typer.Option("--out", "-o", help="Where to write it.")
    ] = Path("videokar.toml"),
    preset: Annotated[
        str | None, typer.Option("--preset", help="Start from a preset instead of the defaults.")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing file.")] = False,
) -> None:
    """Write a configuration file, with every setting explained in place."""
    from .config import ConfigError, resolve_style, to_toml

    if output_path.exists() and not force:
        _fail(f"{output_path} already exists — pass --force to overwrite it")
    try:
        style = resolve_style(preset=preset)
    except ConfigError as exc:
        _fail(str(exc))
    output_path.write_text(to_toml(style), encoding="utf-8")
    console.print(f"wrote {output_path} — edit it, then [bold]videokar render -c {output_path}[/]")


@config_app.command("show")
def config_show(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    preset: Annotated[str | None, typer.Option("--preset")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print as JSON instead of TOML.")] = False,
    schema: Annotated[
        bool, typer.Option("--schema", help="Print the JSON schema of every setting.")
    ] = False,
) -> None:
    """Show the configuration as it resolves, after presets and overrides."""
    from .config import ConfigError, resolve_style, style_schema, to_dict, to_toml

    if schema:
        console.print_json(json.dumps(style_schema()))
        return
    try:
        style = resolve_style(config_path, preset=preset)
    except ConfigError as exc:
        _fail(str(exc))
    if as_json:
        console.print_json(json.dumps(to_dict(style)))
    else:
        console.print(to_toml(style, commented=False))


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
