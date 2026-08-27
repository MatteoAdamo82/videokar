"""Vocal separation with demucs.

The prototype aligned against the full mix and drifted by up to two seconds on
the choruses: a speech model asked to follow a voice through a phaser, a bass
line and a drum kit. Isolating the vocal first is the single biggest accuracy
win in this pipeline, and since separation depends only on the audio, the result
is cached and paid for once per track.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..cache import AudioCache

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "htdemucs"


class SeparationError(RuntimeError):
    """demucs could not separate the track."""


def _import_demucs():
    try:
        import demucs.api  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on install extras
        raise SeparationError(
            "demucs is not installed — install the align extra: "
            'pip install "videokar[align]"'
        ) from exc
    return demucs.api


def resolve_device(requested: str | None = None) -> str:
    """Pick a torch device. 'auto' prefers Apple GPU when it is there."""
    if requested and requested != "auto":
        return requested
    try:
        import torch  # noqa: PLC0415
    except ImportError:  # pragma: no cover - depends on install extras
        return "cpu"
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


@dataclass(frozen=True, slots=True)
class Separation:
    """Where the isolated vocal ended up, and how it got there."""

    vocals_path: Path
    model: str
    device: str
    cached: bool


def separate_vocals(
    audio_path: str | Path,
    *,
    model: str = DEFAULT_MODEL,
    device: str | None = "auto",
    use_cache: bool = True,
) -> Separation:
    """Isolate the vocal stem, reusing a cached result when the audio matches."""
    audio_path = Path(audio_path)
    cache = AudioCache.for_audio(audio_path)
    entry = f"vocals-{model}.wav"

    if use_cache and cache.has(entry):
        logger.info("using cached vocals for %s", audio_path.name)
        return Separation(cache.path(entry), model=model, device="cache", cached=True)

    api = _import_demucs()
    device = resolve_device(device)
    try:
        separator = api.Separator(model=model, device=device, progress=False)
        _, stems = separator.separate_audio_file(audio_path)
    except Exception as exc:
        if device != "cpu":
            # Some demucs/torch combinations still trip over unimplemented MPS
            # kernels. Falling back beats failing the whole run.
            logger.warning("separation on %s failed (%s), retrying on cpu", device, exc)
            separator = api.Separator(model=model, device="cpu", progress=False)
            _, stems = separator.separate_audio_file(audio_path)
            device = "cpu"
        else:
            raise SeparationError(f"demucs failed on {audio_path}: {exc}") from exc

    if "vocals" not in stems:
        raise SeparationError(f"model {model!r} produced no vocals stem: {sorted(stems)}")

    destination = cache.path(entry)
    api.save_audio(stems["vocals"], destination, samplerate=separator.samplerate)
    return Separation(destination, model=model, device=device, cached=False)
