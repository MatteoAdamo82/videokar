"""Finding a font file on this machine."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

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


# Where a font is likely to be on this machine. The working folder is added by
# the caller, so a font dropped next to the song is offered like any other.
FONT_DIRECTORIES = (
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    "/Library/Fonts",
    "~/Library/Fonts",
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "~/.local/share/fonts",
)
FONT_SUFFIXES = {".ttf", ".otf", ".ttc"}


@dataclass(frozen=True, slots=True)
class FontFile:
    path: str
    family: str
    style: str

    @property
    def label(self) -> str:
        return f"{self.family} {self.style}".strip()

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "label": self.label, "family": self.family}


def describe_font(path: Path) -> FontFile | None:
    """Read the family and style out of a font file, or None if it will not open."""
    try:
        font = ImageFont.truetype(str(path), 12)
        family, style = font.getname()
    except (OSError, ValueError):
        # Bitmap fonts, broken files, and collections Pillow will not index.
        return None
    return FontFile(path=str(path), family=family or path.stem, style=style or "")


@lru_cache(maxsize=8)
def _scan(directory: str) -> tuple[FontFile, ...]:
    folder = Path(directory).expanduser()
    if not folder.is_dir():
        return ()
    found = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() in FONT_SUFFIXES and (described := describe_font(path)):
            found.append(described)
    return tuple(found)


def available_fonts(extra: Path | None = None) -> list[FontFile]:
    """Every font this machine can draw with, one entry per file.

    Scanned rather than hardcoded, and cached: reading four hundred font headers
    takes a moment and the answer does not change while the program runs.
    """
    seen: dict[str, FontFile] = {}
    # The working folder first: two files can carry the same family name, and a
    # font deliberately put next to the song should win over the system's copy.
    directories = ([str(extra)] if extra else []) + [*FONT_DIRECTORIES]
    for directory in directories:
        for font in _scan(directory):
            # Apple names its internal fallback faces with a leading dot and
            # does not mean them to be set in; offering them is just noise.
            if font.family.startswith("."):
                continue
            seen.setdefault(font.label, font)
    return sorted(seen.values(), key=lambda f: (f.family.lower(), f.style.lower()))
