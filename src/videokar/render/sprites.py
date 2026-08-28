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


def sprite_has_alpha(path: str) -> bool:
    """True when the file carries transparency worth having."""
    file = Path(path).expanduser()
    if not file.exists():
        return False
    with Image.open(file) as image:
        return "A" in image.convert("RGBA").getbands() and (
            image.convert("RGBA").getchannel("A").getextrema()[0] < 255
        )
