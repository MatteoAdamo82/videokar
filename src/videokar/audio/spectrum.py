"""How loud each band is, frame by frame.

Computed once for the whole song rather than per frame: a four-minute render
asks for six thousand frames, and a short-time Fourier transform over the whole
track costs less than one second of drawing.

Three choices decide whether the result looks like music or like noise.

The bands are spaced logarithmically. An FFT gives linear bins, and a linear
band layout puts the entire bass and most of the interesting middle into the
first two bars while forty bars share the hiss above 10kHz — which is why an
untreated spectrum looks like a cliff falling to nothing.

The magnitudes are in decibels, not amplitudes. Loudness is logarithmic; on a
linear scale everything but the kick drum sits flat against the floor.

And the result is smoothed in time, with a fast attack and a slow release. A
bar that jumps to a value and back within one frame reads as flicker rather
than as a beat; letting it fall slowly is what makes a meter look like it is
responding to music.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..cache import AudioCache
from . import io as audio_io

RATE = 22_050
"""Enough for 11kHz, which is above where a bar still shows anything."""

WINDOW = 2048
"""About 93ms at this rate: long enough to resolve a bass note, short enough
that a bar still lands on the beat rather than after it."""

FLOOR_DB = -70.0
"""Below this a band is drawn as nothing. Not silence — the noise floor of a
mastered track sits well above true zero, and without this every bar keeps a
permanent stump."""

SILENCE_DB = -60.0
"""A track whose loudest band never reaches this has nothing in it, and its
bars stay down rather than being scaled up out of the noise."""

LOW_HZ, HIGH_HZ = 40.0, 11_000.0
"""The band the bars span. Below 40Hz is rumble no speaker reproduces; the top
is what this sample rate can carry."""

ATTACK, RELEASE = 0.55, 0.16
"""How much of a rise, and of a fall, is taken per frame. Rising fast and
falling slowly is what a meter is expected to do."""


@dataclass(frozen=True)
class Spectrum:
    """Band magnitudes, 0 to 1, for every frame of a render."""

    levels: np.ndarray
    """Shape (frames, bands)."""
    fps: float

    @property
    def bands(self) -> int:
        return int(self.levels.shape[1])

    def at(self, time: float) -> np.ndarray:
        """The bands at a point in the song, held at the ends."""
        if self.levels.shape[0] == 0:
            return np.zeros(self.bands, dtype=np.float32)
        index = int(round(time * self.fps))
        return self.levels[min(max(index, 0), self.levels.shape[0] - 1)]


def _band_edges(bands: int, rate: int, window: int) -> list[tuple[int, int]]:
    """FFT bin ranges for logarithmically spaced bands.

    Every band gets at least one bin: at the bottom the spacing is finer than
    the transform can resolve, and a band with no bins would draw a permanent
    gap in the middle of the bars.
    """
    edges = np.geomspace(LOW_HZ, HIGH_HZ, bands + 1)
    bins = np.round(edges * window / rate).astype(int)
    bins = np.clip(bins, 0, window // 2)
    ranges = []
    for index in range(bands):
        low = bins[index]
        high = max(bins[index + 1], low + 1)
        ranges.append((int(low), int(high)))
    return ranges


def analyse(
    samples: np.ndarray, sample_rate: int, *, fps: float, bands: int = 48
) -> Spectrum:
    """Band levels per frame, normalised against the loudest band in the track."""
    step = max(1, int(round(sample_rate / fps)))
    frames = max(1, int(np.ceil(samples.size / step)))
    window = np.hanning(WINDOW).astype(np.float32)
    ranges = _band_edges(bands, sample_rate, WINDOW)

    levels = np.zeros((frames, bands), dtype=np.float32)
    padded = np.zeros(frames * step + WINDOW, dtype=np.float32)
    padded[: samples.size] = samples
    for frame in range(frames):
        # Centred on the frame rather than starting at it, so a bar rises with
        # the beat instead of a window's length after it.
        start = max(0, frame * step - WINDOW // 2)
        chunk = padded[start : start + WINDOW] * window
        power = np.abs(np.fft.rfft(chunk))
        for band, (low, high) in enumerate(ranges):
            # The loudest bin, not the average: a band high up spans far more
            # hertz than one at the bottom, and averaging over that width buries
            # a narrow peak that a listener hears perfectly well.
            levels[frame, band] = power[low:high].max()

    decibels = 20.0 * np.log10(np.maximum(levels, 1e-9))
    loudest = float(decibels.max())
    if loudest < SILENCE_DB:
        # Normalising against the track's own loudest moment is what makes a
        # quiet song legible; on an actually silent one it would turn the noise
        # floor into a full-height wall of bars.
        return Spectrum(levels=np.zeros((frames, bands), dtype=np.float32), fps=fps)
    scaled = (decibels - (loudest + FLOOR_DB)) / -FLOOR_DB
    scaled = np.clip(scaled, 0.0, 1.0)

    smoothed = np.zeros_like(scaled)
    held = np.zeros(bands, dtype=np.float32)
    for frame in range(frames):
        target = scaled[frame]
        rising = target > held
        rate = np.where(rising, ATTACK, RELEASE)
        held = held + (target - held) * rate
        smoothed[frame] = held

    return Spectrum(levels=smoothed, fps=fps)


def spectrum_for(audio_path: str | Path, *, fps: float, bands: int = 48) -> Spectrum:
    """The spectrum of a track, cached beside it."""
    cache = AudioCache.for_audio(audio_path)
    entry = f"spectrum-{bands}-{fps:g}.npz"
    if cache.has(entry):
        with np.load(cache.path(entry)) as stored:
            return Spectrum(levels=stored["levels"], fps=fps)

    with tempfile.TemporaryDirectory(prefix="videokar-spectrum-") as workdir:
        wav = audio_io.decode_to_wav(
            audio_path, Path(workdir) / "spectrum.wav", sample_rate=RATE, mono=True
        )
        samples, rate = audio_io.read_wav(wav)
    spectrum = analyse(samples, rate, fps=fps, bands=bands)
    np.savez_compressed(cache.path(entry), levels=spectrum.levels)
    return spectrum


def describe(spectrum: Spectrum) -> str:
    """A line for the command line: enough to see it found music."""
    return json.dumps(
        {
            "frames": int(spectrum.levels.shape[0]),
            "bands": spectrum.bands,
            "loudest": round(float(spectrum.levels.max()), 3),
            "average": round(float(spectrum.levels.mean()), 3),
        }
    )
