"""Waveform peaks for the sync view.

Dragging a line onto the right beat is guesswork unless you can see where the
phrase actually starts. The peaks come from the isolated vocal stem rather than
the mix, so what you see is the singing and not the drums — which is exactly the
question being asked when a timing looks wrong.

One byte per bucket at a hundred buckets a second: fine enough to place a
syllable, small enough to hand to a browser whole.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from ..cache import AudioCache
from . import io as audio_io

BUCKETS_PER_SECOND = 100


def compute_peaks(
    samples: np.ndarray, sample_rate: int, *, buckets_per_second: int = BUCKETS_PER_SECOND
) -> list[int]:
    """Peak amplitude per bucket, scaled to 0-255 against the loudest bucket."""
    width = max(1, sample_rate // buckets_per_second)
    count = int(np.ceil(samples.size / width))
    padded = np.zeros(count * width, dtype=np.float32)
    padded[: samples.size] = np.abs(samples)
    peaks = padded.reshape(count, width).max(axis=1)
    loudest = float(peaks.max())
    if loudest <= 0:
        return [0] * count
    return np.round(peaks / loudest * 255).astype(np.uint8).tolist()


def peaks_for(
    audio_path: str | Path,
    *,
    vocals_path: str | Path | None = None,
    buckets_per_second: int = BUCKETS_PER_SECOND,
) -> dict:
    """Peaks for a track, cached beside its separated vocal.

    `vocals_path` is what actually gets measured when it is given; the cache is
    still keyed on the original audio, which is what the caller has.
    """
    cache = AudioCache.for_audio(audio_path)
    entry = f"peaks-{buckets_per_second}.json"
    if cache.has(entry):
        return json.loads(cache.path(entry).read_text(encoding="utf-8"))

    source = Path(vocals_path or audio_path)
    with tempfile.TemporaryDirectory(prefix="videokar-peaks-") as workdir:
        wav = audio_io.decode_to_wav(
            source, Path(workdir) / "peaks.wav", sample_rate=16_000, mono=True
        )
        samples, sample_rate = audio_io.read_wav(wav, mono=True)

    payload = {
        "buckets_per_second": buckets_per_second,
        "duration": round(samples.size / sample_rate, 3),
        "source": "vocals" if vocals_path else "mix",
        "peaks": compute_peaks(samples, sample_rate, buckets_per_second=buckets_per_second),
    }
    cache.path(entry).write_text(json.dumps(payload), encoding="utf-8")
    return payload
