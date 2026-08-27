"""Writing a configuration file someone can actually read.

`config init` exists to be edited, so the file it writes carries the schema's
own field descriptions as comments. They come from the same place the validator
and the future editor read, which is the point: one description, not three that
drift apart.
"""

from __future__ import annotations

from typing import Any, get_args, get_origin

from pydantic.fields import FieldInfo

from .loader import to_dict
from .schema import Style

WIDTH = 88


def _fields(kind: type) -> dict[str, FieldInfo]:
    return getattr(kind, "__pydantic_fields__", {})


def _choices(info: FieldInfo) -> str | None:
    """Spell out a Literal's options, so the file lists what is allowed."""
    annotation = info.annotation
    for candidate in (annotation, *get_args(annotation)):
        if get_origin(candidate) is None and getattr(candidate, "__name__", "") == "Literal":
            continue
        options = get_args(candidate)
        if options and all(isinstance(option, str) for option in options):
            return " | ".join(repr(option) for option in options)
    return None


def _bounds(info: FieldInfo) -> str | None:
    parts = []
    for item in info.metadata:
        for name, symbol in (("ge", ">="), ("gt", ">"), ("le", "<="), ("lt", "<")):
            value = getattr(item, name, None)
            if value is not None:
                parts.append(f"{symbol} {value}")
    return ", ".join(parts) or None


def _wrap(text: str, indent: str = "# ") -> list[str]:
    words, lines, current = text.split(), [], indent
    for word in words:
        if len(current) + len(word) + 1 > WIDTH and current != indent:
            lines.append(current)
            current = indent
        current += ("" if current == indent else " ") + word
    if current != indent:
        lines.append(current)
    return lines


def _format(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    return repr(value)


def _assign(name: str, value: Any) -> str:
    """TOML has no null, so an unset value is written commented out.

    Emitting an empty string instead would not validate — size is an int — and
    would read as a deliberate value rather than an absence.
    """
    if value is None:
        return f"# {name} =    # unset"
    return f"{name} = {_format(value)}"


def to_toml(style: Style | None = None, *, commented: bool = True) -> str:
    """Render a style as TOML, optionally with the schema's descriptions."""
    style = style or Style()
    data = to_dict(style)
    out: list[str] = [
        "# videokar — how the video looks.",
        "# Timing lives in the song JSON; nothing here changes when a word is sung,",
        "# so restyling never costs another alignment run.",
        "#",
        '# Build on a preset with:  preset = "youtube"',
        "",
    ]

    for section, info in _fields(Style).items():
        kind = info.annotation
        for option in get_args(kind) or ():
            if option is not type(None):
                kind = option
                break
        section_fields = _fields(kind)
        if not section_fields:
            continue
        values = data.get(section) or {}
        if commented and info.description:
            out += _wrap(info.description)
        out.append(f"[{section}]")
        for name, field_info in section_fields.items():
            if commented:
                if field_info.description:
                    out += _wrap(field_info.description)
                extra = [note for note in (_choices(field_info), _bounds(field_info)) if note]
                if extra:
                    out.append(f"# {'  ·  '.join(extra)}")
            out.append(_assign(name, values.get(name)))
            if commented:
                out.append("")
        if not commented:
            out.append("")
    return "\n".join(out).rstrip() + "\n"
