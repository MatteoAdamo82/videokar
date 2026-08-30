"""`videokar config` — the look of the video: presets and the file over them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from ..config.loader import PRESETS as PRESETS_DIR
from .common import console, fail
from .root import app

config_app = typer.Typer(
    name="config", help="The look of the video: presets and the file that overrides them.",
    no_args_is_help=True,
)
app.add_typer(config_app)


@config_app.command("presets")
def config_presets() -> None:
    """List the built-in presets."""
    from ..config import available_presets, resolve_style

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
    from ..config import ConfigError, resolve_style, to_toml

    if output_path.exists() and not force:
        fail(f"{output_path} already exists — pass --force to overwrite it")
    try:
        style = resolve_style(preset=preset)
    except ConfigError as exc:
        fail(str(exc))
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
    from ..config import ConfigError, resolve_style, style_schema, to_dict, to_toml

    if schema:
        console.print_json(json.dumps(style_schema()))
        return
    try:
        style = resolve_style(config_path, preset=preset)
    except ConfigError as exc:
        fail(str(exc))
    if as_json:
        console.print_json(json.dumps(to_dict(style)))
    else:
        console.print(to_toml(style, commented=False))
