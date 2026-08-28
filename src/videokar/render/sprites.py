"""Loading the image that bounces, when it is not a circle.

Sized by height rather than by its own pixels: the ball's geometry — where it
sits above the text, how high it hops — is already expressed in the text's size,
and a sprite has to obey the same rules or it lands somewhere else than the
circle would. So whatever the file's resolution, it is scaled to the diameter
the circle would have had.

Measured on what is actually drawn, not on the canvas. A PNG exported with
transparent margins would otherwise come out smaller than the circle it replaced
by exactly however much padding the artist happened to leave, which is not
something anyone should have to crop out by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image


class SpriteError(RuntimeError):
    """The image that was meant to bounce cannot be used."""


@lru_cache(maxsize=16)
def load_sprite(path: str, height: int) -> Image.Image:
    """Read a PNG and scale it to `height`, keeping its aspect and its alpha."""
    file = Path(path).expanduser()
    if not file.exists():
        raise SpriteError(f"sprite not found: {file}")
    try:
        image = Image.open(file)
        image.load()
    except OSError as exc:
        raise SpriteError(f"{file} is not an image Pillow can read: {exc}") from exc

    image = image.convert("RGBA")
    if image.height == 0 or image.width == 0:
        raise SpriteError(f"{file} has no pixels")

    visible = image.getbbox()
    if visible is None:
        raise SpriteError(f"{file} is entirely transparent — nothing would be drawn")
    image = image.crop(visible)

    width = max(1, round(image.width * height / image.height))
    return image.resize((width, max(1, height)), Image.LANCZOS)


@dataclass(frozen=True, slots=True)
class SpriteReport:
    """What a candidate image is, and how it will come out."""

    canvas: tuple[int, int]
    visible: tuple[int, int]
    """Size of the part that is actually drawn, after transparent margins."""

    transparent: bool
    padding: float
    """Fraction of the canvas that is empty margin."""

    @property
    def warnings(self) -> list[str]:
        notes = []
        if not self.transparent:
            notes.append(
                "no transparency — this will bounce as a solid rectangle over the words. "
                "Export it as a PNG with an alpha channel."
            )
        if self.padding > 0.5:
            notes.append(
                f"{self.padding:.0%} of the file is empty margin. Harmless — it is measured "
                "on what it draws — but the file is mostly nothing."
            )
        return notes

    def drawn_at(self, diameter: int) -> tuple[int, int]:
        width = max(1, round(self.visible[0] * diameter / self.visible[1]))
        return (width, diameter)


def inspect_sprite(path: str | Path) -> SpriteReport:
    """Measure an image before it is used, so surprises come early."""
    file = Path(path).expanduser()
    if not file.exists():
        raise SpriteError(f"sprite not found: {file}")
    try:
        with Image.open(file) as opened:
            image = opened.convert("RGBA")
    except OSError as exc:
        raise SpriteError(f"{file} is not an image Pillow can read: {exc}") from exc

    box = image.getbbox()
    if box is None:
        raise SpriteError(f"{file} is entirely transparent — nothing would be drawn")
    visible = (box[2] - box[0], box[3] - box[1])
    area = image.width * image.height
    return SpriteReport(
        canvas=image.size,
        visible=visible,
        transparent=image.getchannel("A").getextrema()[0] < 255,
        padding=1 - (visible[0] * visible[1]) / area if area else 0.0,
    )
