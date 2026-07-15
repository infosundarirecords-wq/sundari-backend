"""
dsp.py
======
Core signal-processing primitives used to actually RENDER audio according
to the Decision Engine's output (decision_schema.py). Yeh module Phase 4
ke JSON decisions (EQ bands, compression, de-esser, saturation, stereo
width, limiter) ko real waveform transformations mein badalta hai —
JUCE plugin (real-time, Logic Pro ke andar) jo karta hai, uska
offline/batch Python equivalent, website ke liye.

Sab functions (channels, samples) shape float64 numpy arrays par kaam
karte hain, jaisa analysis/loader.py deta hai.
"""

from __future__ import annotations

import numpy as np
from scipy import signal


# ---------------------------------------------------------------------------
# EQ — RBJ Audio EQ Cookbook biquad coefficients
# ---------------------------------------------------------------------------

def _biquad_coeffs(filter_type: str, freq_hz: float, gain_db: float, q: float, sr: int):
    freq_hz = min(max(freq_hz, 10.0), sr / 2 - 10.0)
    w0 = 2 * np.pi * freq_hz / sr
    cos_w0 = np.cos(w0)
    sin_w0 = np.sin(w0)
    A = 10 ** (gain_db / 40.0)
    alpha = sin_w0 / (2 * max(q, 0.05))

    if filter_type == "bell":
        b0 = 1 + alpha * A
        b1 = -2 * cos_w0
        b2 = 1 - alpha * A
        a0 = 1 + alpha / A
        a1 = -2 * cos_w0
        a2 = 1 - alpha / A
    elif filter_type == "low_shelf":
        sq = 2 * np.sqrt(A) * alpha
        b0 = A * ((A + 1) - (A - 1) * cos_w0 + sq)
        b1 = 2 * A * ((A - 1) - (A + 1) * cos_w0)
        b2 = A * ((A + 1) - (A - 1) * cos_w0 - sq)
        a0 = (A + 1) + (A - 1) * cos_w0 + sq
        a1 = -2 * ((A - 1) + (A + 1) * cos_w0)
        a2 = (A + 1) + (A - 1) * cos_w0 - sq
    elif filter_type == "high_shelf":
        sq = 2 * np.sqrt(A) * alpha
        b0 = A * ((A + 1) + (A - 1) * cos_w0 + sq)
        b1 = -2 * A * ((A - 1) + (A + 1) * cos_w0)
        b2 = A * ((A + 1) + (A - 1) * cos_w0 - sq)
        a0 = (A + 1) - (A - 1) * cos_w0 + sq
        a1 = 2 * ((A - 1) - (A + 1) * cos_w0)
        a2 = (A + 1) - (A - 1) * cos_w0 - sq
    elif filter_type == "high_pass":
        b0 = (1 + cos_w0) / 2
        b1 = -(1 + cos_w0)
        b2 = (1 + cos_w0) / 2
        a0 = 1 + alpha
        a1 = -2 * cos_w0
        a2 = 1 - alpha
    elif filter_type == "low_pass":
        b0 = (1 - cos_w0) / 2
        b1 = 1 - cos_w0
        b2 = (1 - cos_w0) / 2
        a0 = 1 + alpha
        a1 = -2 * cos_w0
        a2 = 1 - alpha
    elif filter_type == "notch":
        b0 = 1
        b1 = -2 * cos_w0
        b2 = 1
        a0 = 1 + alpha
        a1 = -2 * cos_w0
        a2 = 1 - alpha
    else:
        raise ValueError(f"Unknown filter_type: {filter_type}")

    return np.array([b0 / a0, b1 / a0, b2 / a0]), np.array([1.0, a1 / a0, a2 / a0])


def apply_eq_band(audio: np.ndarray, sr: int, freq_hz: float, gain_db: float,
                   q: float, filter_type: str) -> np.ndarray:
    """audio: (channels, samples). Ek single EQ band lagata hai, sab channels par."""
    if abs(gain_db) < 0.05 and filter_type not in ("high_pass", "low_pass", "notch"):
        return audio
    b, a = _biquad_coeffs(filter_type, freq_hz, gain_db, q, sr)
    sos = signal.tf2sos(b, a)
    out = np.empty_like(audio)
    for ch in range(audio.shape[0]):
        out[ch] = signal.sosfilt(sos, audio[ch])
    return out


def apply_eq_chain(audio: np.ndarray, sr: int, bands: list[dict]) -> np.ndarray:
    for band in bands:
        audio = apply_eq_band(
            audio, sr,
            freq_hz=band["frequency_hz"], gain_db=band["gain_db"],
            q=band["q_factor"], filter_type=band["filter_type"],
        )
    return audio


# ---------------------------------------------------------------------------
# Dynamics — feed-forward compressor with attack/release envelope
# ---------------------------------------------------------------------------

def _envelope_follower(rectified: np.ndarray, sr: int, attack_ms: float, release_ms: float) -> np.ndarray:
    attack_coef = np.exp(-1.0 / (sr * max(attack_ms, 0.1) / 1000.0))
    release_coef = np.exp(-1.0 / (sr * max(release_ms, 1.0) / 1000.0))
    env = np.zeros_like(rectified)
    prev = 0.0
    for i in range(rectified.shape[0]):
        x = rectified[i]
        coef = attack_coef if x > prev else release_coef
        prev = coef * prev + (1 - coef) * x
        env[i] = prev
    return env


def apply_compressor(audio: np.ndarray, sr: int, threshold_db: float, ratio: float,
                      attack_ms: float, release_ms: float, makeup_gain_db: float) -> np.ndarray:
    """audio: (channels, samples). Stereo-linked (dono channels ka max envelope share hota hai)."""
    eps = 1e-9
    mono_detect = np.max(np.abs(audio), axis=0)  # link channels via max
    env = _envelope_follower(mono_detect, sr, attack_ms, release_ms)
    env_db = 20 * np.log10(np.maximum(env, eps))

    over_db = np.maximum(env_db - threshold_db, 0.0)
    gain_reduction_db = over_db * (1.0 - 1.0 / max(ratio, 1.0))
    gain_lin = 10 ** ((-gain_reduction_db + makeup_gain_db) / 20.0)

    return audio * gain_lin[np.newaxis, :]


def apply_deesser(audio: np.ndarray, sr: int, freq_low: float, freq_high: float,
                   reduction_db: float, attack_ms: float = 3.0, release_ms: float = 60.0) -> np.ndarray:
    """Sirf sibilance band (freq_low-freq_high) par dynamic reduction — baaki signal untouched."""
    center = (freq_low + freq_high) / 2.0
    bandwidth = max(freq_high - freq_low, 200.0)
    q = center / bandwidth
    sos_band = signal.tf2sos(*_biquad_coeffs("bell", center, 0.0, q, sr))

    out = np.empty_like(audio)
    for ch in range(audio.shape[0]):
        band = signal.sosfilt(sos_band, audio[ch])
        env = _envelope_follower(np.abs(band), sr, attack_ms, release_ms)
        # threshold ~ RMS of the band itself, taki sirf peaks reduce hon
        thresh = np.sqrt(np.mean(band ** 2)) + 1e-6
        reduction = np.clip((env - thresh) / (thresh + 1e-9), 0, 1) * (reduction_db / 20.0 * np.log(10))
        gain = np.exp(-reduction)
        band_reduced = band * gain
        out[ch] = audio[ch] - band + band_reduced
    return out


def apply_saturation(audio: np.ndarray, amount_percent: float) -> np.ndarray:
    """Simple tanh soft-clip saturation, amount 0-100."""
    drive = 1.0 + (max(amount_percent, 0.0) / 100.0) * 4.0
    return np.tanh(audio * drive) / np.tanh(drive)


# ---------------------------------------------------------------------------
# Stereo imaging
# ---------------------------------------------------------------------------

def to_stereo(audio: np.ndarray) -> np.ndarray:
    if audio.shape[0] == 1:
        return np.vstack([audio[0], audio[0]])
    return audio[:2]


def apply_stereo_width(audio: np.ndarray, width_adjustment_percent: float) -> np.ndarray:
    stereo = to_stereo(audio)
    mid = (stereo[0] + stereo[1]) / 2.0
    side = (stereo[0] - stereo[1]) / 2.0
    factor = 1.0 + (width_adjustment_percent / 100.0)
    factor = max(factor, 0.0)
    side = side * factor
    left = mid + side
    right = mid - side
    return np.vstack([left, right])


def apply_pan(audio: np.ndarray, pan_position: float) -> np.ndarray:
    """Equal-power pan. pan_position: -1 (left) .. +1 (right). Mono source assumed
    (agar stereo hai to dono channels par hi apply hota hai, simple approximation)."""
    stereo = to_stereo(audio)
    angle = (pan_position + 1.0) * (np.pi / 4.0)  # 0..pi/2
    left_gain = np.cos(angle)
    right_gain = np.sin(angle)
    return np.vstack([stereo[0] * left_gain, stereo[1] * right_gain])


def apply_clip_gain(audio: np.ndarray, gain_db: float) -> np.ndarray:
    if abs(gain_db) < 0.01:
        return audio
    return audio * (10 ** (gain_db / 20.0))


# ---------------------------------------------------------------------------
# Master bus — limiter + LUFS matching
# ---------------------------------------------------------------------------

def apply_limiter(audio: np.ndarray, ceiling_dbtp: float, release_ms: float = 50.0, sr: int = 44100) -> np.ndarray:
    """Simple lookahead-free brick-wall limiter: peak envelope follow + gain reduction."""
    ceiling_lin = 10 ** (ceiling_dbtp / 20.0)
    peak = np.max(np.abs(audio), axis=0)
    release_coef = np.exp(-1.0 / (sr * max(release_ms, 1.0) / 1000.0))

    gain = np.ones_like(peak)
    current_gain = 1.0
    for i in range(peak.shape[0]):
        needed = ceiling_lin / peak[i] if peak[i] > ceiling_lin else 1.0
        if needed < current_gain:
            current_gain = needed  # instant attack, no overshoot allowed
        else:
            current_gain = release_coef * current_gain + (1 - release_coef) * needed
        current_gain = min(current_gain, 1.0)
        gain[i] = current_gain

    limited = audio * gain[np.newaxis, :]
    # final hard safety clip, just in case
    return np.clip(limited, -ceiling_lin, ceiling_lin)


def match_lufs(audio: np.ndarray, sr: int, target_lufs: float, measure_lufs_fn) -> np.ndarray:
    """audio ko gain adjust karke target_lufs ke kareeb laata hai (ek measurement pass)."""
    result = measure_lufs_fn(audio, sr)
    current = result.integrated_lufs
    if not np.isfinite(current):
        return audio
    gain_db = target_lufs - current
    gain_db = max(min(gain_db, 24.0), -24.0)  # sanity clamp
    return audio * (10 ** (gain_db / 20.0))
