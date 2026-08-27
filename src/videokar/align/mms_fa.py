"""Forced alignment with torchaudio's MMS_FA bundle.

Two things make this work on sung audio where the prototype's speech model did
not. The first is the input: a demucs vocal stem rather than the full mix. The
second is the star token, `*`, which MMS_FA can emit for audio that matches
nothing in the transcript — an instrumental break, an ad-lib, a producer tag.

Stars go *between lines*, not between words. Measured on the reference track the
two placements score the same, but a star between every pair of words also lets
the aligner drop a second of silence into the middle of a phrase: the worst
intra-line gap nearly doubles, from 0.98s to 1.80s. Between lines is where a
singer actually stops.

The emission model runs happily on the Apple GPU; `forced_align` itself has no
MPS kernel, so the Viterbi pass always comes back to the CPU. That split is
handled here rather than being the caller's problem.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import numpy as np

from .base import Aligner, AlignmentError, AlignmentResult, WordTiming

logger = logging.getLogger(__name__)

STAR = "*"

# MMS_FA convolutional frontend stride: one emission frame per 320 input samples
# at 16 kHz, i.e. 20 ms. The frontend also swallows part of a frame at each end
# of whatever it is given, so chunk boundaries are overlapped and the affected
# frames thrown away rather than concatenated blind — otherwise every boundary
# shifts everything after it by another 20 ms.
_SAMPLES_PER_FRAME = 320
_OVERLAP_FRAMES = 32


class MMSForcedAligner(Aligner):
    """Character-level CTC forced alignment, multilingual, star-token capable."""

    name = "MMS_FA"

    def __init__(
        self,
        *,
        device: str | None = "auto",
        chunk_seconds: float = 60.0,
        use_star: bool = True,
    ) -> None:
        self._device_request = device
        self._chunk_seconds = chunk_seconds
        self._use_star = use_star
        self._model = None
        self._tokenizer = None
        self._aligner = None
        self._device = "cpu"

    @property
    def sample_rate(self) -> int:
        return 16_000

    @property
    def device(self) -> str:
        return self._device

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch  # noqa: PLC0415
            import torchaudio  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on install extras
            raise AlignmentError(
                "torchaudio is not installed — install the align extra: "
                'pip install "videokar[align]"'
            ) from exc

        from ..audio.separate import resolve_device  # noqa: PLC0415

        device = resolve_device(self._device_request)
        bundle = torchaudio.pipelines.MMS_FA
        model = bundle.get_model(with_star=self._use_star).eval()
        try:
            model = model.to(device)
        except (RuntimeError, NotImplementedError) as exc:  # pragma: no cover
            logger.warning("could not place the alignment model on %s (%s), using cpu", device, exc)
            device, model = "cpu", model.to("cpu")

        self._torch = torch
        self._model = model
        self._tokenizer = bundle.get_tokenizer()
        self._aligner = bundle.get_aligner()
        self._device = device

    def _emissions(self, samples: np.ndarray):
        """Run the acoustic model over the track, one bounded chunk at a time.

        Self-attention is quadratic in the number of frames, so a three minute
        track in one pass would want gigabytes of attention matrix. Chunking
        keeps that bounded; the overlap keeps it accurate.
        """
        torch = self._torch
        waveform = torch.from_numpy(np.ascontiguousarray(samples, dtype=np.float32))[None, :]
        total = waveform.shape[1]
        chunk = max(
            _SAMPLES_PER_FRAME,
            int(self._chunk_seconds * self.sample_rate) // _SAMPLES_PER_FRAME * _SAMPLES_PER_FRAME,
        )
        overlap = _OVERLAP_FRAMES * _SAMPLES_PER_FRAME

        pieces = []
        with torch.inference_mode():
            for offset in range(0, total, chunk):
                left_pad = min(offset, overlap)
                right_pad = min(total - (offset + chunk), overlap)
                right_pad = max(right_pad, 0)
                window = waveform[:, offset - left_pad : offset + chunk + right_pad]
                emission, _ = self._model(window.to(self._device))
                frames = emission[0].cpu()
                # Back to the CPU immediately: the Viterbi pass runs there, and
                # holding every chunk on the GPU would defeat the chunking.
                start = _OVERLAP_FRAMES if left_pad else 0
                stop = frames.shape[0] - (_OVERLAP_FRAMES if right_pad else 0)
                pieces.append(frames[start:stop])
        return torch.cat(pieces, dim=0)

    def align(self, samples: np.ndarray, groups: Sequence[Sequence[str]]) -> AlignmentResult:
        words = [word for group in groups for word in group]
        if not words:
            raise AlignmentError("no words to align")
        self._load()

        emission = self._emissions(samples)
        frame_duration = samples.size / emission.shape[0] / self.sample_rate

        transcript: list[str] = []
        positions: list[int] = []
        group_of: list[int] = []
        for group_index, group in enumerate(groups):
            if self._use_star:
                transcript.append(STAR)
            for word in group:
                positions.append(len(transcript))
                group_of.append(group_index)
                transcript.append(word)
        if self._use_star:
            transcript.append(STAR)

        try:
            spans = self._aligner(emission, self._tokenizer(transcript))
        except Exception as exc:
            raise AlignmentError(
                f"forced alignment failed over {len(words)} words "
                f"and {emission.shape[0]} frames: {exc}"
            ) from exc

        timings = []
        for index, position in enumerate(positions):
            token_spans = spans[position]
            weighted = sum(float(s.score) * (s.end - s.start) for s in token_spans)
            length = sum(s.end - s.start for s in token_spans) or 1
            timings.append(
                WordTiming(
                    index=index,
                    group=group_of[index],
                    word=words[index],
                    start=round(token_spans[0].start * frame_duration, 3),
                    end=round(token_spans[-1].end * frame_duration, 3),
                    score=round(weighted / length, 4),
                )
            )

        return AlignmentResult(
            words=timings,
            model=self.name,
            device=self._device,
            frame_duration=frame_duration,
        )
