"""The audio half of the pipeline: mixdown in, timed words out.

Kept separate from both the CLI and the JSON writer so that the expensive part
— separate, detect, align — can be driven from a test, a notebook or the web UI
without dragging along a command-line parser or a file format.
"""

from __future__ import annotations

import logging
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .align.base import AlignmentResult
from .align.mms_fa import MMSForcedAligner
from .audio import io as audio_io
from .audio.separate import Separation, separate_vocals
from .audio.vad import Region, detect_onsets, detect_vocal_regions
from .lyrics import ParsedLyrics

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AlignedTrack:
    """Everything the JSON writer needs, and nothing about how it will look."""

    audio: audio_io.AudioInfo
    lyrics: ParsedLyrics
    alignment: AlignmentResult
    regions: list[Region]
    onsets: list[float]
    """Where the voice attacks, for checking a line's start against."""

    separation: Separation | None
    elapsed: float


def run_alignment(
    audio_path: str | Path,
    lyrics: ParsedLyrics,
    *,
    separate: bool = True,
    separation_model: str = "htdemucs",
    device: str | None = "auto",
    use_cache: bool = True,
    aligner: MMSForcedAligner | None = None,
) -> AlignedTrack:
    """Separate, detect vocal regions, and time every word of `lyrics`.

    With `separate=False` the alignment runs against the full mix, which is
    faster and noticeably less accurate — useful for a quick look, not for a
    final render.
    """
    started = time.perf_counter()
    audio_path = Path(audio_path)
    info = audio_io.probe(audio_path)

    separation = None
    source = audio_path
    if separate:
        separation = separate_vocals(
            audio_path, model=separation_model, device=device, use_cache=use_cache
        )
        source = separation.vocals_path
        logger.info("vocals: %s (cached=%s)", source, separation.cached)

    aligner = aligner or MMSForcedAligner(device=device)
    with tempfile.TemporaryDirectory(prefix="videokar-") as workdir:
        mono = audio_io.decode_to_wav(
            source,
            Path(workdir) / "aligner-input.wav",
            sample_rate=aligner.sample_rate,
            mono=True,
        )
        samples, sample_rate = audio_io.read_wav(mono, mono=True)

    regions = detect_vocal_regions(samples, sample_rate)
    onsets = detect_onsets(samples, sample_rate)
    logger.info(
        "%d vocal regions and %d attacks over %.1fs", len(regions), len(onsets), info.duration
    )

    result = aligner.align(samples, lyrics.word_groups)
    return AlignedTrack(
        audio=info,
        lyrics=lyrics,
        alignment=result,
        regions=regions,
        onsets=onsets,
        separation=separation,
        elapsed=time.perf_counter() - started,
    )


def onsets_for(audio_path: str | Path, *, separate: bool = True) -> list[float]:
    """Vocal attacks for a track, cached beside its separated vocal.

    So that a document written before onsets existed can still be checked
    against them without being aligned again.
    """
    import json  # noqa: PLC0415

    from .cache import AudioCache  # noqa: PLC0415

    audio_path = Path(audio_path)
    cache = AudioCache.for_audio(audio_path)
    entry = "onsets.json"
    if cache.has(entry):
        return json.loads(cache.path(entry).read_text(encoding="utf-8"))

    source = audio_path
    if separate:
        source = separate_vocals(audio_path).vocals_path
    with tempfile.TemporaryDirectory(prefix="videokar-onsets-") as workdir:
        mono = audio_io.decode_to_wav(
            source, Path(workdir) / "onsets.wav", sample_rate=16_000, mono=True
        )
        samples, sample_rate = audio_io.read_wav(mono, mono=True)

    onsets = detect_onsets(samples, sample_rate)
    cache.path(entry).write_text(json.dumps(onsets), encoding="utf-8")
    return onsets
