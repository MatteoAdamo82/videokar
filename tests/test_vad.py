import numpy as np
import pytest

from videokar.audio.vad import (
    Region,
    detect_vocal_regions,
    frame_energy_db,
    gaps_between,
    total_voiced,
)

SR = 16_000


def tone(seconds: float, *, amplitude: float = 0.5, freq: float = 220.0) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def silence(seconds: float, *, amplitude: float = 0.0) -> np.ndarray:
    noise = np.random.default_rng(0).normal(0, 1, int(seconds * SR)).astype(np.float32)
    return (noise * amplitude).astype(np.float32)


def test_finds_two_regions_around_a_gap():
    signal = np.concatenate([silence(1.0), tone(2.0), silence(2.0), tone(1.5), silence(1.0)])
    regions = detect_vocal_regions(signal, SR)
    assert len(regions) == 2
    assert regions[0].start == pytest.approx(1.0, abs=0.15)
    assert regions[0].end == pytest.approx(3.0, abs=0.15)
    assert regions[1].start == pytest.approx(5.0, abs=0.15)


def test_short_gaps_are_breaths_not_boundaries():
    signal = np.concatenate([tone(1.0), silence(0.1), tone(1.0)])
    assert len(detect_vocal_regions(signal, SR)) == 1


def test_a_silent_stem_has_no_regions():
    assert detect_vocal_regions(silence(3.0, amplitude=1e-6), SR) == []


def test_quiet_master_is_handled_by_the_relative_threshold():
    loud = np.concatenate([silence(0.5), tone(1.0), silence(0.5)])
    quiet = loud * 0.01
    assert len(detect_vocal_regions(quiet, SR)) == len(detect_vocal_regions(loud, SR)) == 1


def test_bleed_shorter_than_min_region_is_dropped():
    signal = np.concatenate([silence(1.0), tone(0.05), silence(1.0), tone(1.0), silence(0.5)])
    assert len(detect_vocal_regions(signal, SR, pad=0.0)) == 1


def test_energy_of_an_input_shorter_than_one_frame():
    energy, _ = frame_energy_db(np.zeros(10, dtype=np.float32), SR)
    assert energy.size == 0


def test_gaps_are_the_complement_of_the_regions():
    regions = [Region(1.0, 2.0), Region(4.0, 5.0)]
    gaps = [g.as_tuple() for g in gaps_between(regions, 6.0)]
    assert gaps == [(0.0, 1.0), (2.0, 4.0), (5.0, 6.0)]
    assert total_voiced(regions) == pytest.approx(2.0)


def test_no_regions_means_the_whole_track_is_a_gap():
    assert [g.as_tuple() for g in gaps_between([], 3.0)] == [(0.0, 3.0)]


def test_region_containment_has_a_tolerance():
    region = Region(1.0, 2.0)
    assert region.contains(1.5)
    assert not region.contains(2.4)
    assert region.contains(2.4, tolerance=0.5)
