"""Reading the look of a video from a TOML file.

Resolution order, each layer overriding the one before: built-in defaults, then
a named preset, then the user's file, then whatever was passed on the command
line. Merging is per key rather than per section, so setting one colour does not
silently reset the rest of the block around it.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from .schema import Style

PRESETS = Path(__file__).parent / "presets"
ADAPTER = TypeAdapter(Style)


class ConfigError(ValueError):
    """The configuration cannot be read, or does not describe a valid style."""


def available_presets() -> list[str]:
    return sorted(path.stem for path in PRESETS.glob("*.toml"))


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc


def merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursive per-key merge. Overlay wins; None in the overlay is ignored."""
    result = dict(base)
    for key, value in overlay.items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = value
    return result


def resolve_style(
    config_path: str | Path | None = None,
    *,
    preset: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> Style:
    """Build the style from presets, a file and command-line overrides."""
    layers: dict[str, Any] = {}

    if preset:
        if preset not in available_presets():
            raise ConfigError(
                f"unknown preset {preset!r} — one of {', '.join(available_presets())}"
            )
        layers = merge(layers, _read_toml(PRESETS / f"{preset}.toml"))

    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise ConfigError(f"config file not found: {path}")
        data = _read_toml(path)
        # A file may name the preset it builds on, so a project keeps one entry
        # point instead of a file plus a flag someone forgets.
        named = data.pop("preset", None)
        if named and not preset:
            layers = merge(_read_toml(PRESETS / f"{named}.toml"), layers)
        layers = merge(layers, data)

    if overrides:
        layers = merge(layers, overrides)

    try:
        return ADAPTER.validate_python(layers)
    except ValidationError as exc:
        raise ConfigError(_explain(exc, config_path)) from exc


def _explain(error: ValidationError, path: str | Path | None) -> str:
    where = f"in {path}" if path else "in the configuration"
    lines = [f"{len(error.errors())} problem(s) {where}:"]
    for problem in error.errors():
        location = ".".join(str(part) for part in problem["loc"] if part != "function-after")
        lines.append(f"  {location or '(root)'}: {problem['msg']}")
    return "\n".join(lines)


def style_schema() -> dict[str, Any]:
    """JSON schema for the whole style, for building an editor from."""
    return ADAPTER.json_schema()


def to_dict(style: Style) -> dict[str, Any]:
    return ADAPTER.dump_python(style, mode="json")
