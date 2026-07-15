"""
metrics.py
==========
Core level & loudness metrics for the Sundari AI Mix Engineer analysis engine.

Why implemented manually with numpy/scipy instead of only relying on a
third-party library:
- LUFS (integrated loudness) is standardized in ITU-R BS.1770-4. Implementing
  the K-weighting filter and gating logic ourselves means the engine has
  zero hard dependency on any single external loudness library and the
  math is auditable/testable. `pyloudnorm` (listed in requirements.txt) can
  still be used as a cross-check / drop-in in a later phase, but the core
  engine must not silently fail if that package is missing on a user's
  machine, so we ship our own reference implementation.
- RMS, Peak, and Dynamic Range (Crest Factor + a simplified "DR" style
  measurement inspired by the TT DR Meter methodology) are computed
  directly from the waveform for full control over windowing.

All functions accept a mono or multi-channel numpy array shaped
(channels, samples) or (samples,) for mono, plus the sample rate.
"""

from __future__ import annotations

import numpy as np
from scipy import signal
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_2d(audio: np.ndarray) -> np.ndarray:
    """Ensure audio is shaped (channels, samples)."""
    if audio.ndim == 1:
        return audio[np.newaxis, :]
    return audio


def _db(value: float, ref: float = 1.0, floor_db: float = -120.0) -> float:
    """Convert linear amplitude/power ratio to dBFS, with a safety floor."""
    if value <= 0:
        return floor_db
    return max(20.0 * np.log10(value / ref), floor_db)


# ---------------------------------------------------------------------------
# K-weighting filter (ITU-R BS.1770-4)
# ---------------------------------------------------------------------------

def _k_weighting_filter(sr: int):
    """
    Returns second-order-section filter coefficients implementing the
    two-stage K-weighting filter from ITU-R BS.1770-4:
      Stage 1: a shelving filter that models the acoustic effect of the head.
      Stage 2: a high-pass filter (RLB weighting curve).

    Coefficients are derived using the standard bilinear-transform formulas
    from the spec (pre-warped for the given sample rate) rather than hard
    -coded 48kHz-only constants, so the filter is correct at any sample rate
    (44.1k, 48k, 96k, etc.).
    """
    # Stage 1: High-frequency shelving filter (head model)
    f0 = 1681.9744509555319
    G = 3.99984385397
    Q = 0.7071752369554196

    K = np.tan(np.pi * f0 / sr)
    Vh = 10 ** (G / 20)
    Vb = Vh ** 0.4996667741545416

    a0 = 1 + K / Q + K * K
    b0 = (Vh + Vb * K / Q + K * K) / a0
    b1 = 2 * (K * K - Vh) / a0
    b2 = (Vh - Vb * K / Q + K * K) / a0
    a1 = 2 * (K * K - 1) / a0
    a2 = (1 - K / Q + K * K) / a0
    stage1_b = [b0, b1, b2]
    stage1_a = [1.0, a1, a2]

    # Stage 2: High-pass filter (RLB weighting)
    f0_hp = 38.13547087613982
    Q_hp = 0.5003270373238773
    K_hp = np.tan(np.pi * f0_hp / sr)
    a0_hp = 1 + K_hp / Q_hp + K_hp * K_hp
    b0_hp = 1.0
    b1_hp = -2.0
    b2_hp = 1.0
    a1_hp = 2 * (K_hp * K_hp - 1) / a0_hp
    a2_hp = (1 - K_hp / Q_hp + K_hp * K_hp) / a0_hp
    stage2_b = [b0_hp / a0_hp, b1_hp / a0_hp, b2_hp / a0_hp]
    stage2_a = [1.0, a1_hp, a2_hp]

    return (stage1_b, stage1_a), (stage2_b, stage2_a)


def _apply_k_weighting(mono: np.ndarray, sr: int) -> np.ndarray:
    (b1, a1), (b2, a2) = _k_weighting_filter(sr)
    y = signal.lfilter(b1, a1, mono)
    y = signal.lfilter(b2, a2, y)
    return y


# Channel weighting per ITU-R BS.1770 for standard configurations.
# For stereo (the common case for a mix), both channels weight 1.0.
_CHANNEL_WEIGHTS_STEREO = [1.0, 1.0]


@dataclass
class LoudnessResult:
    integrated_lufs: float
    momentary_max_lufs: float
    short_term_max_lufs: float
    loudness_range_lu: float


def measure_lufs(audio: np.ndarray, sr: int) -> LoudnessResult:
    """
    Computes integrated loudness (LUFS) per ITU-R BS.1770-4, plus momentary
    and short-term maxima and an approximate Loudness Range (LRA), using
    a simplified two-stage relative + absolute gating scheme (per spec:
    absolute gate at -70 LUFS, relative gate at -10 LU below the ungated
    mean).
    """
    audio = _to_2d(audio)
    n_channels, n_samples = audio.shape

    weights = _CHANNEL_WEIGHTS_STEREO if n_channels == 2 else [1.0] * n_channels

    # K-weight each channel independently, then sum weighted mean-square
    weighted_channels = [
        _apply_k_weighting(audio[ch], sr) for ch in range(n_channels)
    ]

    block_size = int(0.4 * sr)       # 400 ms gating blocks
    step_size = int(block_size * 0.25)  # 75% overlap (100 ms hop)

    if n_samples < block_size:
        block_size = n_samples
        step_size = max(block_size, 1)

    block_loudness = []
    for start in range(0, n_samples - block_size + 1, step_size):
        z_sum = 0.0
        for ch, w in enumerate(weights):
            block = weighted_channels[ch][start:start + block_size]
            z_sum += w * np.mean(block ** 2)
        if z_sum > 0:
            block_loudness.append(-0.691 + 10 * np.log10(z_sum))

    if not block_loudness:
        return LoudnessResult(-70.0, -70.0, -70.0, 0.0)

    block_loudness = np.array(block_loudness)

    # Absolute gate at -70 LUFS
    gated = block_loudness[block_loudness > -70.0]
    if len(gated) == 0:
        return LoudnessResult(-70.0, -70.0, -70.0, 0.0)

    ungated_mean = 10 * np.log10(np.mean(10 ** (gated / 10)))
    relative_threshold = ungated_mean - 10.0

    final_gated = gated[gated > relative_threshold]
    if len(final_gated) == 0:
        final_gated = gated

    integrated = 10 * np.log10(np.mean(10 ** (final_gated / 10)))

    # Momentary (400ms, no overlap needed for max) and short-term (3s) maxima
    momentary_max = float(np.max(block_loudness)) if len(block_loudness) else -70.0

    st_block = int(3.0 * sr)
    st_step = int(st_block * 0.25) if st_block > 0 else 1
    st_values = []
    mono_sum = np.sum(
        [w * (weighted_channels[ch] ** 2) for ch, w in enumerate(weights)], axis=0
    )
    if n_samples >= st_block and st_block > 0:
        for start in range(0, n_samples - st_block + 1, max(st_step, 1)):
            seg_mean = np.mean(mono_sum[start:start + st_block])
            if seg_mean > 0:
                st_values.append(-0.691 + 10 * np.log10(seg_mean))
    short_term_max = float(np.max(st_values)) if st_values else integrated

    lra = float(
        np.percentile(final_gated, 95) - np.percentile(final_gated, 10)
    ) if len(final_gated) > 1 else 0.0

    return LoudnessResult(
        integrated_lufs=round(float(integrated), 2),
        momentary_max_lufs=round(momentary_max, 2),
        short_term_max_lufs=round(short_term_max, 2),
        loudness_range_lu=round(lra, 2),
    )


# ---------------------------------------------------------------------------
# Peak, RMS, Dynamic Range
# ---------------------------------------------------------------------------

def measure_peak_dbfs(audio: np.ndarray) -> float:
    """Sample peak level in dBFS (0 dBFS = full scale = amplitude of 1.0)."""
    audio = _to_2d(audio)
    peak = np.max(np.abs(audio))
    return round(_db(peak), 2)


def measure_true_peak_dbtp(audio: np.ndarray, sr: int, oversample: int = 4) -> float:
    """
    Approximates true peak (inter-sample peak) per ITU-R BS.1770 Annex 2 by
    oversampling with polyphase resampling and measuring the peak of the
    oversampled signal. This catches inter-sample peaks that a simple
    sample-peak reading would miss and that can cause clipping after D/A
    conversion or lossy encoding even when sample peak reads under 0 dBFS.
    """
    audio = _to_2d(audio)
    peaks = []
    for ch in range(audio.shape[0]):
        oversampled = signal.resample_poly(audio[ch], oversample, 1)
        peaks.append(np.max(np.abs(oversampled)))
    return round(_db(max(peaks)), 2)


def measure_rms_dbfs(audio: np.ndarray) -> float:
    """Overall RMS level in dBFS across all channels combined."""
    audio = _to_2d(audio)
    rms = np.sqrt(np.mean(audio ** 2))
    return round(_db(rms), 2)


@dataclass
class DynamicRangeResult:
    crest_factor_db: float
    dr_value: float


def measure_dynamic_range(audio: np.ndarray, sr: int) -> DynamicRangeResult:
    """
    Crest Factor: peak-to-RMS ratio in dB (simple, whole-file measure).

    DR value: a simplified version of the well-known "DR" (Dynamic Range)
    meter methodology used in mastering — the track is split into 3-second
    blocks; for each block the peak and RMS are measured; the DR value is
    derived from the second-loudest peak values vs the RMS of the top 20%
    loudest blocks. This is a simplification of the official TT DR Meter
    algorithm (which is not publicly specified in full, closed reference
    implementation) but follows the same block-based peak-vs-RMS logic and
    gives directionally correct, comparable results (roughly: DR14+ is very
    dynamic/unmastered-sounding, DR4-DR7 is heavily limited/loud-war mastered).
    """
    audio = _to_2d(audio)
    mono = np.mean(audio, axis=0)

    peak = np.max(np.abs(mono))
    rms = np.sqrt(np.mean(mono ** 2))
    crest_factor = _db(peak) - _db(rms)

    block_len = int(3.0 * sr)
    if block_len <= 0 or len(mono) < block_len:
        return DynamicRangeResult(round(crest_factor, 2), round(crest_factor, 2))

    n_blocks = len(mono) // block_len
    block_peaks = []
    block_rms = []
    for i in range(n_blocks):
        seg = mono[i * block_len:(i + 1) * block_len]
        block_peaks.append(np.max(np.abs(seg)))
        block_rms.append(np.sqrt(np.mean(seg ** 2)))

    block_peaks = np.array(block_peaks)
    block_rms = np.array(block_rms)

    # Take the top 20% loudest blocks by RMS
    n_top = max(1, int(0.2 * n_blocks))
    top_idx = np.argsort(block_rms)[-n_top:]

    # Second-highest peak among the top-loudest blocks (avoids one transient
    # skewing the result, matching the spirit of the DR meter approach)
    top_peaks_sorted = np.sort(block_peaks[top_idx])[::-1]
    ref_peak = top_peaks_sorted[1] if len(top_peaks_sorted) > 1 else top_peaks_sorted[0]

    rms_of_top = np.sqrt(np.mean(block_rms[top_idx] ** 2))

    dr_value = _db(ref_peak) - _db(rms_of_top)

    return DynamicRangeResult(
        crest_factor_db=round(float(crest_factor), 2),
        dr_value=round(float(dr_value), 2),
    )


# ---------------------------------------------------------------------------
# Clipping detection
# ---------------------------------------------------------------------------

@dataclass
class ClippingResult:
    is_clipping: bool
    clipped_sample_count: int
    clipped_percentage: float
    max_consecutive_clipped: int


def detect_clipping(audio: np.ndarray, threshold: float = 0.999) -> ClippingResult:
    """
    Flags samples at/above `threshold` (default just under full scale to
    account for floating point/dither noise) as clipped, and additionally
    looks for consecutive flat-topped runs (a stronger signature of real
    clipping than isolated full-scale samples, which can occur naturally
    at a single peak).
    """
    audio = _to_2d(audio)
    abs_audio = np.abs(audio)
    clipped_mask = abs_audio >= threshold

    total_clipped = int(np.sum(clipped_mask))
    total_samples = abs_audio.size
    percentage = round(100.0 * total_clipped / total_samples, 4) if total_samples else 0.0

    max_run = 0
    for ch in range(clipped_mask.shape[0]):
        runs = np.diff(
            np.where(
                np.concatenate(([clipped_mask[ch][0]],
                                 clipped_mask[ch][:-1] != clipped_mask[ch][1:],
                                 [True]))
            )[0]
        )[::2]
        if clipped_mask[ch][0]:
            runs = runs[0:] if len(runs) else runs
        if len(runs) > 0:
            max_run = max(max_run, int(np.max(runs)))

    return ClippingResult(
        is_clipping=total_clipped > 0 and max_run >= 3,
        clipped_sample_count=total_clipped,
        clipped_percentage=percentage,
        max_consecutive_clipped=max_run,
    )
