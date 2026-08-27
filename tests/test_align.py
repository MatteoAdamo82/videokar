import numpy as np
import pytest

from videokar.align.base import Aligner, AlignmentError, AlignmentResult, WordTiming
from videokar.align.mms_fa import MMSForcedAligner
from videokar.audio.separate import resolve_device


class FakeAligner(Aligner):
    """Spreads the words evenly: enough to exercise everything downstream."""

    name = "fake"

    @property
    def sample_rate(self) -> int:
        return 16_000

    def align(self, samples, groups):
        flat = [(g, w) for g, group in enumerate(groups) for w in group]
        duration = samples.size / self.sample_rate
        step = duration / max(len(flat), 1)
        return AlignmentResult(
            words=[
                WordTiming(i, g, w, round(i * step, 3), round((i + 1) * step, 3), 0.9)
                for i, (g, w) in enumerate(flat)
            ],
            model=self.name,
            device="cpu",
            frame_duration=0.02,
        )


def test_fake_aligner_satisfies_the_interface():
    result = FakeAligner().align(np.zeros(16_000 * 4, dtype=np.float32), [["a"], ["b"]])
    assert [w.word for w in result.words] == ["a", "b"]
    assert [w.group for w in result.words] == [0, 1]
    assert result.words[0].duration == pytest.approx(2.0)


def test_timings_are_monotonic_by_construction():
    result = FakeAligner().align(np.zeros(16_000 * 3, dtype=np.float32), [list("abc"), list("def")])
    starts = [w.start for w in result.words]
    assert starts == sorted(starts)
    pairs = zip(result.words, result.words[1:], strict=False)
    assert all(a.end <= b.start + 1e-6 for a, b in pairs)


def test_aligning_nothing_is_an_error_before_the_model_is_touched():
    # Fails fast: no 1.2 GB checkpoint gets loaded to align an empty list.
    with pytest.raises(AlignmentError, match="no words"):
        MMSForcedAligner().align(np.zeros(16_000, dtype=np.float32), [[], []])


def test_mms_expects_16k():
    assert MMSForcedAligner().sample_rate == 16_000


@pytest.mark.parametrize("requested", ["cpu", "cuda", "mps"])
def test_an_explicit_device_is_respected(requested):
    assert resolve_device(requested) == requested


def test_auto_device_is_something_torch_can_use():
    assert resolve_device("auto") in {"cpu", "cuda", "mps"}
