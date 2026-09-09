"""One frame of a background clip, so the still in the dialog does not lie.

The renderer leaves clips to ffmpeg, which only happens while encoding. The
preview has no encode to hang that on, so it asks ffmpeg for the one frame it
needs and hands it over as a picture.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path
from tempfile import gettempdir

from fastapi import HTTPException


@lru_cache(maxsize=8)
def clip_seconds(clip: str) -> float:
    """How long a clip runs, so the preview wraps round it the way a render does."""
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", clip],
            capture_output=True, text=True, check=True,
        )  # fmt: skip
        return max(0.1, float(probe.stdout.strip()))
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        raise HTTPException(422, f"{Path(clip).name} could not be read as a video") from exc


@lru_cache(maxsize=32)
def clip_still(clip: str, second: int) -> str:
    """A frame from a clip, cached: a slider drag asks for the same one often."""
    shot = Path(gettempdir()) / f"videokar-still-{abs(hash((clip, second)))}.png"
    if shot.is_file():
        return str(shot)
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", clip, "-ss", str(second),
             "-frames:v", "1", str(shot)],
            check=True, capture_output=True,
        )  # fmt: skip
    except (OSError, subprocess.CalledProcessError) as exc:
        raise HTTPException(422, f"{Path(clip).name} could not be read as a video") from exc
    if not shot.is_file():
        # Past the end of a short clip: ffmpeg writes nothing and says nothing.
        raise HTTPException(422, f"{Path(clip).name} has no frame at {second}s")
    return str(shot)


def still_for(clip: Path, at: float) -> str:
    """The frame a looping clip would be showing at this point in the song."""
    return clip_still(str(clip), int(at % clip_seconds(str(clip))))


def forget_stills() -> None:
    clip_still.cache_clear()
    clip_seconds.cache_clear()
