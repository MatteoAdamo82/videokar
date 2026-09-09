"""Reading the music: which bands move, and how they move."""

from __future__ import annotations

import numpy as np

from videokar.audio.spectrum import ATTACK, RELEASE, analyse

RATE = 22_050


def tone(hz: float, seconds: float = 2.0, level: float = 0.5) -> np.ndarray:
    t = np.linspace(0, seconds, int(RATE * seconds), dtype=np.float32)
    return (np.sin(2 * np.pi * hz * t) * level).astype(np.float32)


def loudest_band(spectrum, when: float) -> int:
    return int(np.argmax(spectrum.at(when)))


def test_a_low_note_moves_a_low_band_and_a_high_one_a_high_band():
    low = analyse(tone(80), RATE, fps=25, bands=32)
    high = analyse(tone(5000), RATE, fps=25, bands=32)
    assert loudest_band(low, 1.0) < 8
    assert loudest_band(high, 1.0) > 20


def test_both_reach_the_top_of_their_scale():
    # Bands high up span far more hertz than bands at the bottom. Averaging over
    # that width would bury a treble note that is perfectly audible.
    for hz in (80, 5000):
        spectrum = analyse(tone(hz), RATE, fps=25, bands=32)
        assert spectrum.at(1.0).max() > 0.9, hz


def test_silence_stays_down():
    # Levels are scaled against the track's own loudest moment, which is what
    # makes a quiet song legible — and would turn a silent one into a wall.
    spectrum = analyse(np.zeros(RATE * 2, dtype=np.float32), RATE, fps=25, bands=16)
    assert spectrum.levels.max() == 0.0


def test_a_very_quiet_track_is_still_read():
    # Quiet is not silent: a track mixed low should still draw bars.
    spectrum = analyse(tone(200, level=0.02), RATE, fps=25, bands=16)
    assert spectrum.levels.max() > 0.9


def test_bars_rise_faster_than_they_fall():
    # A bar that drops the instant the note does reads as flicker; falling
    # slowly is what makes a meter look like it is following music. Measured as
    # the time to cross the same threshold going up and coming back down, so
    # what is compared is the smoothing and not the note's own envelope.
    burst = np.concatenate([tone(400, 0.4), np.zeros(int(RATE * 0.6), dtype=np.float32)])
    spectrum = analyse(burst.astype(np.float32), RATE, fps=50, bands=16)
    trace = spectrum.levels[:, loudest_band(spectrum, 0.2)]
    peak = int(np.argmax(trace))
    half = trace[peak] * 0.5

    rising = next(i for i in range(peak + 1) if trace[i] >= half)
    falling = next(i for i in range(peak, trace.size) if trace[i] < half) - peak
    assert falling > rising, (rising, falling)
    assert ATTACK > RELEASE


def test_the_frame_rate_decides_how_many_frames():
    for fps in (25, 50):
        spectrum = analyse(tone(300, 2.0), RATE, fps=fps, bands=8)
        assert abs(spectrum.levels.shape[0] - 2 * fps) <= 1
        assert spectrum.fps == fps


def test_asking_past_the_end_holds_the_last_frame():
    spectrum = analyse(tone(300, 1.0), RATE, fps=25, bands=8)
    assert np.array_equal(spectrum.at(99.0), spectrum.levels[-1])
    assert np.array_equal(spectrum.at(-5.0), spectrum.levels[0])


def test_every_band_gets_at_least_one_bin():
    # Log spacing at the bottom is finer than the transform can resolve; a band
    # with no bins would be a permanent gap in the middle of the bars.
    spectrum = analyse(tone(400), RATE, fps=25, bands=120)
    assert spectrum.bands == 120
    assert np.isfinite(spectrum.levels).all()
