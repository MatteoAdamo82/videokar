"""Finding a font file on this machine."""

from __future__ import annotations

from pathlib import Path

# Tried in order when no font file is given. A missing font is a hard error
# rather than a silent fallback to Pillow's bitmap default, which renders at
# roughly ten pixels and would look like a bug.
FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


class FontError(RuntimeError):
    """No usable font file."""


def resolve_font_path(candidate: str | None) -> Path:
    """Find a font file, or say clearly that there is none."""
    if candidate:
        path = Path(candidate).expanduser()
        if not path.exists():
            raise FontError(f"font file not found: {path}")
        return path
    for option in FONT_CANDIDATES:
        path = Path(option)
        if path.exists():
            return path
    raise FontError("no default font found on this system — pass one explicitly with --font")
