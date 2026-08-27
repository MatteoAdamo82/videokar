"""Audio decoding and probing, delegated to ffmpeg.

Everything that touches container formats goes through ffmpeg rather than a
Python decoder: it is already a hard requirement for encoding the video, and it
reads whatever a user drops on it — mp3, wav, aif, m4a, flac.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf


class FFmpegMissingError(RuntimeError):
    """ffmpeg or ffprobe is not on the PATH."""


class AudioDecodeError(RuntimeError):
    """ffmpeg could not read the input file."""


def require_ffmpeg() -> None:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise FFmpegMissingError(
            f"{' and '.join(missing)} not found on PATH — install it (macOS: brew install ffmpeg)"
        )


@dataclass(frozen=True, slots=True)
class AudioInfo:
    path: Path
    duration: float
    sample_rate: int
    channels: int


def probe(path: str | Path) -> AudioInfo:
    """Read duration, sample rate and channel count without decoding."""
    require_ffmpeg()
    path = Path(path)
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=sample_rate,channels:format=duration",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )  # fmt: skip
    if result.returncode != 0:
        raise AudioDecodeError(f"ffprobe failed on {path}: {result.stderr.strip()}")
    payload = json.loads(result.stdout)
    streams = payload.get("streams") or []
    if not streams:
        raise AudioDecodeError(f"{path} has no audio stream")
    return AudioInfo(
        path=path,
        duration=float(payload["format"]["duration"]),
        sample_rate=int(streams[0]["sample_rate"]),
        channels=int(streams[0]["channels"]),
    )


def decode_to_wav(
    source: str | Path,
    destination: str | Path,
    *,
    sample_rate: int | None = None,
    mono: bool = False,
) -> Path:
    """Decode any input to a PCM wav, optionally resampled and downmixed."""
    require_ffmpeg()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source)]
    if mono:
        command += ["-ac", "1"]
    if sample_rate is not None:
        command += ["-ar", str(sample_rate)]
    command += ["-c:a", "pcm_s16le", str(destination)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AudioDecodeError(f"ffmpeg failed on {source}: {result.stderr.strip()}")
    return destination


def read_wav(path: str | Path, *, mono: bool = True) -> tuple[np.ndarray, int]:
    """Read a wav into float32 samples. Mono downmix is an unweighted average."""
    samples, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
    if mono:
        samples = samples.mean(axis=1)
    return samples, sample_rate
