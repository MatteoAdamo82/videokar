"""The aligner interface.

Alignment is the one stage most likely to be swapped out — MMS_FA today,
whisperx or something newer tomorrow — so the rest of the pipeline only ever
sees this contract: samples and words in, one timing per word out.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


class AlignmentError(RuntimeError):
    """The aligner could not time the given words against the given audio."""


@dataclass(frozen=True, slots=True)
class WordTiming:
    """When one word was sung."""

    index: int
    """Position in the flattened word list handed to the aligner."""

    group: int
    """Which group — in practice which lyric line — the word came from."""

    word: str
    start: float
    end: float
    score: float
    """Mean per-character probability, 0..1. Low means the aligner was guessing."""

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class AlignmentResult:
    words: list[WordTiming]
    model: str
    device: str
    frame_duration: float
    """Seconds per emission frame — the resolution of every timing above."""


class Aligner(ABC):
    """Times a known word sequence against audio that sings it."""

    name: str = "aligner"

    @property
    @abstractmethod
    def sample_rate(self) -> int:
        """Sample rate the aligner expects its input in."""

    @abstractmethod
    def align(self, samples: np.ndarray, groups: Sequence[Sequence[str]]) -> AlignmentResult:
        """Time words against mono `samples` at `self.sample_rate`.

        Words arrive grouped — one group per lyric line. The grouping is not
        cosmetic: it tells the aligner where a long silence is plausible and
        where it is not. Singers pause between lines, not in the middle of one.
        """
