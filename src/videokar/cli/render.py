"""`videokar render` — draw the karaoke overlay and encode it.

The heavy imports are inside the command: `videokar --help` should not wait on
torch and PIL to tell you what the commands are.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .common import console, fail, open_song, resolve_audio, without_none
from .root import app

# Everything Pillow reads as a still; anything else goes to ffmpeg as a clip.
PICTURES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}


def _is_picture(path: Path) -> bool:
    return path.suffix.lower() in PICTURES


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
    behind: Annotated[
        Path | None,
        typer.Option("--behind", help="A still or a clip to put behind the words."),
    ] = None,
    dim: Annotated[
        float | None,
        typer.Option("--dim", help="Darken the background this much, 0 to 1."),
    ] = None,
) -> None:
    """Draw the karaoke overlay and encode it."""
    from ..config import ConfigError, resolve_style
    from ..render import CODECS, EncodeError, FontError, FrameRenderer
    from ..render.background import BackgroundError
    from ..render.encode import render_png_sequence, render_segmented
    from ..render.sprites import SpriteError

    # Command-line flags are the last layer over presets and the file, so an
    # unset flag has to be absent rather than a default that silently wins.
    overrides = {
        "output": without_none(
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
        "main": without_none(
            {"font": str(font) if font else None, "size": font_size, "min_scale": min_scale}
        ),
        "ball": without_none(
            {
                "kind": "sprite" if sprite else None,
                "sprite": str(sprite) if sprite else None,
                "sprite_scale": sprite_scale,
            }
        ),
        # A still or a clip, told apart by the suffix rather than by two flags:
        # there is only ever one thing behind the words.
        "background": without_none(
            {
                "image": str(behind) if behind and _is_picture(behind) else None,
                "video": str(behind) if behind and not _is_picture(behind) else None,
                "dim": dim,
            }
        ),
    }

    try:
        style = resolve_style(config_path, preset=preset, overrides=without_none(overrides))
    except ConfigError as exc:
        fail(str(exc))

    if style.output.format not in CODECS:
        fail(f"unknown format {style.output.format!r} — one of {', '.join(sorted(CODECS))}")
    if style.output.format == "mp4" and style.output.background[3] < 255:
        # H.264 has no alpha, so a transparent background would silently become
        # black. Say so rather than surprising anyone with it.
        console.print("[yellow]note:[/yellow] mp4 has no alpha — compositing onto black")
        style = _with_opaque_background(style)

    song = open_song(song_path)

    try:
        renderer = FrameRenderer(song, style)
    except (FontError, SpriteError, BackgroundError) as exc:
        fail(str(exc))
    if not renderer.cues:
        fail("nothing to draw — every line is unsung or untimed")

    output = style.output
    wants_audio = output.audio and output.format != "png"
    audio_file = resolve_audio(song, song_path) if wants_audio else None
    if wants_audio and audio_file is None:
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
                    background=style.background,
                    on_segment=progress,
                )
    except (EncodeError, OSError) as exc:
        fail(str(exc))

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



def _with_opaque_background(style):
    from dataclasses import replace

    red, green, blue, _ = style.output.background
    return replace(style, output=replace(style.output, background=(red, green, blue, 255)))
