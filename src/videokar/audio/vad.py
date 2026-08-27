"""Where the singing actually happens, measured on the isolated vocal stem.

A forced aligner has to place every word somewhere, so when the lyrics run out
before the audio does it smears the remaining words across the instrumental
break. Knowing which stretches of the track carry a voice gives the aligner a
reality check: words landing outside a vocal region are almost certainly wrong,
and long stretches of silence tell the renderer to park the ball.

Energy thresholding is enough here because the input is a demucs vocal stem, not
a full mix — what is left between phrases is bleed and noise, tens of dB below
the singing. That keeps the dependency list short: no second neural model.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_EPSILON = 1e-10


@dataclass(frozen=True, slots=True)
class Region:
    """A stretch of audio carrying voice."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start

    def contains(self, time: float, *, tolerance: float = 0.0) -> bool:
        return self.start - tolerance <= time <= self.end + tolerance

    def as_tuple(self) -> tuple[float, float]:
        return (self.start, self.end)


def frame_energy_db(
    samples: np.ndarray,
    sample_rate: int,
    *,
    frame_seconds: float = 0.025,
    hop_seconds: float = 0.010,
) -> tuple[np.ndarray, float]:
    """RMS energy per frame in dBFS, plus the hop length in seconds."""
    frame_length = max(1, int(round(frame_seconds * sample_rate)))
    hop_length = max(1, int(round(hop_seconds * sample_rate)))
    if samples.size < frame_length:
        return np.array([]), hop_seconds

    frame_count = 1 + (samples.size - frame_length) // hop_length
    strides = np.lib.stride_tricks.as_strided(
        samples,
        shape=(frame_count, frame_length),
        strides=(samples.strides[0] * hop_length, samples.strides[0]),
    )
    rms = np.sqrt(np.mean(np.square(strides, dtype=np.float64), axis=1))
    return 20.0 * np.log10(rms + _EPSILON), hop_length / sample_rate


def detect_vocal_regions(
    samples: np.ndarray,
    sample_rate: int,
    *,
    threshold_db: float = -38.0,
    hysteresis_db: float = 6.0,
    floor_db: float = -60.0,
    min_region: float = 0.20,
    min_silence: float = 0.35,
    pad: float = 0.10,
) -> list[Region]:
    """Find the sung stretches of a vocal stem.

    `threshold_db` is relative to the loudest frame, so it survives a quiet
    master. `floor_db` is the absolute backstop that keeps a purely relative
    threshold honest: on an instrumental, where the stem holds nothing but
    separation artefacts, the loudest frame is still noise and everything near
    it would otherwise be reported as singing.

    A frame opens a region above the threshold and only closes it
    `hysteresis_db` below, which stops a region flickering apart on the decay of
    a held note. Regions shorter than `min_region` are dropped as bleed, gaps
    shorter than `min_silence` are treated as breaths rather than boundaries,
    and `pad` widens the result so an onset is never clipped.
    """
    energy, hop = frame_energy_db(np.ascontiguousarray(samples, dtype=np.float32), sample_rate)
    if energy.size == 0:
        return []

    peak = float(energy.max())
    if peak < floor_db:
        return []
    open_at = max(peak + threshold_db, floor_db)
    close_at = open_at - hysteresis_db

    spans: list[list[float]] = []
    active = False
    start_index = 0
    for index, value in enumerate(energy):
        if not active and value >= open_at:
            active, start_index = True, index
        elif active and value < close_at:
            active = False
            spans.append([start_index * hop, index * hop])
    if active:
        spans.append([start_index * hop, energy.size * hop])

    merged: list[list[float]] = []
    for span in spans:
        if merged and span[0] - merged[-1][1] < min_silence:
            merged[-1][1] = span[1]
        else:
            merged.append(span)

    duration = samples.size / sample_rate
    return [
        Region(start=max(0.0, start - pad), end=min(duration, end + pad))
        for start, end in merged
        if end - start >= min_region
    ]


def total_voiced(regions: list[Region]) -> float:
    return sum(region.duration for region in regions)


def in_any_region(time: float, regions: list[Region], *, tolerance: float = 0.0) -> bool:
    return any(region.contains(time, tolerance=tolerance) for region in regions)


def gaps_between(regions: list[Region], duration: float) -> list[Region]:
    """The instrumental stretches: everything the regions do not cover."""
    result: list[Region] = []
    cursor = 0.0
    for region in regions:
        if region.start > cursor:
            result.append(Region(cursor, region.start))
        cursor = max(cursor, region.end)
    if cursor < duration:
        result.append(Region(cursor, duration))
    return result
