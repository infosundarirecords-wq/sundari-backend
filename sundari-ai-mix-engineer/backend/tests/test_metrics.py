"""
test_metrics.py
================
Unit tests for the analysis engine, validated against synthetic signals
with mathematically known properties (pure sine waves, controlled
clipping, controlled phase relationships). This is how the correctness
of DSP code should be proven — not just "it ran without an exception."

Run with:
    cd backend && pytest -v
"""

import numpy as np
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.analysis.engine import AnalysisEngine
from app.analysis.metrics import detect_clipping, measure_dynamic_range
from app.analysis.stereo import analyze_stereo
from app.analysis.spectral import detect_mud, detect_harshness, detect_frequency_masking

SR = 44100
DURATION = 4.0


def sine(freq, amp=1.0, duration=DURATION, sr=SR):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return amp * np.sin(2 * np.pi * freq * t)


@pytest.fixture
def engine():
    return AnalysisEngine()


def test_peak_and_rms_of_known_sine(engine):
    amp = 10 ** (-18 / 20)  # -18 dBFS
    mono = sine(1000, amp)
    stereo = np.stack([mono, mono])
    result = engine.analyze_track(stereo, SR, "test")
    assert abs(result.peak_dbfs - (-18.0)) < 0.1
    # RMS of a pure sine = peak / sqrt(2) => -18 - 3.01 = -21.01 dBFS
    assert abs(result.rms_dbfs - (-21.01)) < 0.1


def test_crest_factor_of_pure_sine_is_3db(engine):
    mono = sine(1000, 0.5)
    stereo = np.stack([mono, mono])
    result = engine.analyze_track(stereo, SR, "test")
    assert abs(result.crest_factor_db - 3.01) < 0.05


def test_clipping_detected_when_signal_exceeds_full_scale():
    raw = 2.5 * sine(1000, 1.0)
    clipped = np.clip(raw, -1.0, 1.0)
    result = detect_clipping(np.stack([clipped, clipped]))
    assert result.is_clipping is True
    assert result.clipped_percentage > 50.0


def test_clean_signal_not_flagged_as_clipping():
    clean = sine(1000, 0.5)
    result = detect_clipping(np.stack([clean, clean]))
    assert result.is_clipping is False


def test_identical_channels_have_correlation_one():
    mono = sine(1000, 0.5)
    result = analyze_stereo(np.stack([mono, mono]))
    assert abs(result.correlation - 1.0) < 0.01


def test_inverted_channel_has_correlation_negative_one():
    mono = sine(1000, 0.5)
    result = analyze_stereo(np.stack([mono, -mono]))
    assert abs(result.correlation - (-1.0)) < 0.01
    assert result.mono_compatibility_risk == "high"


def test_mono_input_flagged_correctly():
    mono = sine(1000, 0.5)
    result = analyze_stereo(mono)
    assert result.is_mono is True


def test_mud_detected_for_low_mid_heavy_signal():
    np.random.seed(1)
    muddy = 0.6 * sine(350, 1.0) + 0.05 * np.random.randn(int(SR * DURATION))
    result = detect_mud(np.stack([muddy, muddy]), SR)
    assert result.detected is True


def test_harshness_detected_for_upper_mid_heavy_signal():
    np.random.seed(1)
    harsh = 0.6 * sine(3500, 1.0) + 0.05 * np.random.randn(int(SR * DURATION))
    result = detect_harshness(np.stack([harsh, harsh]), SR)
    assert result.detected is True


def test_frequency_masking_flags_overlapping_same_level_tones():
    a = sine(85, 0.5)
    b = sine(88, 0.5)
    conflicts = detect_frequency_masking(np.stack([a, a]), np.stack([b, b]), SR)
    bands_flagged = [c.band for c in conflicts]
    assert "bass" in bands_flagged


def test_frequency_masking_not_flagged_when_one_dominates():
    a = sine(85, 0.9)
    b = sine(88, 0.01)  # 39dB quieter -> should not be flagged as competing
    conflicts = detect_frequency_masking(np.stack([a, a]), np.stack([b, b]), SR)
    bands_flagged = [c.band for c in conflicts]
    assert "bass" not in bands_flagged


def test_silence_does_not_crash_engine(engine):
    silence = np.zeros((2, SR * 2))
    result = engine.analyze_track(silence, SR, "silence")
    assert result.peak_dbfs <= -100
    assert result.clipping_detected is False
