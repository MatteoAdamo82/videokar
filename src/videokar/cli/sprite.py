"""`videokar sprite` — is this PNG usable, and is it big enough?"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .common import console, fail
from .root import app


@app.command("sprite")
def sprite_cmd(
    image: Annotated[Path, typer.Argument(help="PNG you want to bounce.")],
    width: Annotated[int, typer.Option("--width")] = 1920,
    height: Annotated[int, typer.Option("--height")] = 1080,
    scale: Annotated[float, typer.Option("--scale", help="Size relative to the circle.")] = 1.0,
) -> None:
    """Check an image before using it: is it usable, and is it big enough?"""
    from ..config import Output, Style
    from ..config.schema import resolved_ball, resolved_size
    from ..render.sprites import SpriteError, inspect_sprite

    try:
        report = inspect_sprite(image)
    except SpriteError as exc:
        fail(str(exc))

    style = Style(output=Output(width=width, height=height))
    ball = resolved_ball(style.ball, resolved_size(style.main, style.output))
    diameter = max(1, round(ball.radius * 2 * scale))
    drawn = report.drawn_at(diameter)

    console.print(f"[bold]{image.name}[/bold]")
    console.print(f"  canvas          {report.canvas[0]}x{report.canvas[1]}")
    console.print(f"  actually drawn  {report.visible[0]}x{report.visible[1]}")
    console.print(
        f"  transparency    {'yes' if report.transparent else '[red]none[/red]'}"
    )
    console.print(f"  at {width}x{height}, scale {scale}: drawn {drawn[0]}x{drawn[1]} pixels")

    # Downscaling is free and looks good; upscaling is what shows.
    if report.visible[1] < drawn[1]:
        console.print(
            f"[yellow]too small[/yellow] — it would be stretched from {report.visible[1]} to "
            f"{drawn[1]} pixels tall and look soft. Twice {drawn[1]} is plenty."
        )
    elif report.visible[1] > drawn[1] * 8:
        console.print(
            f"[dim]larger than it needs to be — {report.visible[1]} pixels tall for a "
            f"{drawn[1]} pixel draw. Harmless, just a bigger file.[/dim]"
        )
    else:
        console.print("[green]good size[/green]")

    for note in report.warnings:
        console.print(f"[yellow]note:[/yellow] {note}")

