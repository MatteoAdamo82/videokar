"""What sits behind the words.

A still is loaded once and fitted to the frame here; a clip is left to the
encoder, which has ffmpeg to hand and no reason to decode video through Pillow
one frame at a time.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageEnhance

from ..config.schema import Background


class BackgroundError(RuntimeError):
    """The background could not be used."""


def fit_image(image: Image.Image, size: tuple[int, int], how: str) -> Image.Image:
    """Fit a picture to the frame, by one of the three ways of meaning "fit"."""
    width, height = size
    if how == "stretch":
        return image.resize(size, Image.LANCZOS)

    scale = max(width / image.width, height / image.height)
    if how == "contain":
        scale = min(width / image.width, height / image.height)
    scaled = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.LANCZOS,
    )
    # Centred either way: cover crops the overflow evenly, contain pads it.
    canvas = Image.new("RGBA", size, (0, 0, 0, 255))
    canvas.paste(scaled, ((width - scaled.width) // 2, (height - scaled.height) // 2))
    return canvas


@lru_cache(maxsize=4)
def _load(path: str, size: tuple[int, int], how: str, dim: float) -> Image.Image:
    try:
        with Image.open(path) as handle:
            source = handle.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise BackgroundError(f"{Path(path).name} could not be read as a picture: {exc}") from exc

    fitted = fit_image(source, size, how)
    if dim:
        # Brightness rather than a black veil over the top: a veil would also
        # wash out the colours, and what is wanted is a darker photograph, not
        # a greyer one.
        fitted = ImageEnhance.Brightness(fitted).enhance(1.0 - dim)
        fitted.putalpha(255)
    return fitted


def base_frame(
    background: Background, size: tuple[int, int], fill: tuple[int, int, int, int]
) -> Image.Image:
    """The layer every frame starts from.

    Loaded once and copied per frame: the fitting and the dimming are the same
    for every one of them, and a four-minute render asks for six thousand.
    """
    if background.video:
        # The clip is composited by ffmpeg when encoding, so what is drawn here
        # has to be see-through for it to show at all.
        return Image.new("RGBA", size, (0, 0, 0, 0))
    if not background.image:
        return Image.new("RGBA", size, fill)
    return _load(background.image, size, background.fit, background.dim).copy()


def forget_images() -> None:
    """Drop the cache — for the tests, and for a file replaced under us."""
    _load.cache_clear()
