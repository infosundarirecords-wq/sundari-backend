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

def envelope_follower(rectified: np.ndarray, sr: int, attack_ms: float, release_ms: float) -> np.ndarray:
    """
    Attack/release envelope follower.

    PERFORMANCE NOTE: ek per-sample Python for-loop 3-4 minute ke gaane
    (~10 million samples) par itna slow hota hai ki Render jaisa free-tier
    server timeout ho jaata hai (502 Bad Gateway). Isliye yahan "control-rate"
    trick use kiya hai — jo real compressors bhi karte hain: har chhote
    block (64 samples) ka sirf ek representative (max) value nikaal ke,
    us chhoti si series par hi Python loop chalate hain (~150x kam
    iterations), phir wapas poori length tak upsample kar dete hain.
    Audio-quality par asar nahi padta (64 samples @ 44.1kHz ~1.4ms
    resolution, kaan usse fine detail sun hi nahi paate is context mein).
    """
    block = max(1, sr // 150)  # ~1.4ms blocks -> control rate ~700Hz
    n = rectified.shape[0]
    n_blocks = (n + block - 1) // block
    padded_len = n_blocks * block
    if padded_len != n:
        rectified = np.pad(rectified, (0, padded_len - n))
    block_max = rectified.reshape(n_blocks, block).max(axis=1)

    attack_coef = np.exp(-1.0 / (max(sr / block, 1.0) * max(attack_ms, 0.1) / 1000.0))
    release_coef = np.exp(-1.0 / (max(sr / block, 1.0) * max(release_ms, 1.0) / 1000.0))

    env_blocks = np.zeros_like(block_max)
    prev = 0.0
    for i in range(n_blocks):
        x = block_max[i]
        coef = attack_coef if x > prev else release_coef
        prev = coef * prev + (1 - coef) * x
        env_blocks[i] = prev

    env = np.repeat(env_blocks, block)[:n]
    return env


def apply_compressor(audio: np.ndarray, sr: int, threshold_db: float, ratio: float,
                      attack_ms: float, release_ms: float, makeup_gain_db: float) -> np.ndarray:
    """audio: (channels, samples). Stereo-linked (dono channels ka max envelope share hota hai)."""
    eps = 1e-9
    mono_detect = np.max(np.abs(audio), axis=0)  # link channels via max
    env = envelope_follower(mono_detect, sr, attack_ms, release_ms)
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
        env = envelope_follower(np.abs(band), sr, attack_ms, release_ms)
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
    """
    Simple lookahead-free brick-wall limiter: peak envelope follow + gain reduction.

    PERFORMANCE NOTE: same block-rate trick as envelope_follower (see
    comment there) — avoids a slow per-sample Python loop on real-length
    songs. A final np.clip() safety net still guarantees the true ceiling
    is never exceeded, even at block resolution.
    """
    ceiling_lin = 10 ** (ceiling_dbtp / 20.0)
    peak = np.max(np.abs(audio), axis=0)

    block = max(1, sr // 150)
    n = peak.shape[0]
    n_blocks = (n + block - 1) // block
    padded_len = n_blocks * block
    if padded_len != n:
        peak = np.pad(peak, (0, padded_len - n), constant_values=0.0)
    peak_blocks = peak.reshape(n_blocks, block).max(axis=1)

    release_coef = np.exp(-1.0 / (max(sr / block, 1.0) * max(release_ms, 1.0) / 1000.0))

    gain_blocks = np.ones_like(peak_blocks)
    current_gain = 1.0
    for i in range(n_blocks):
        needed = ceiling_lin / peak_blocks[i] if peak_blocks[i] > ceiling_lin else 1.0
        if needed < current_gain:
            current_gain = needed  # instant attack, no overshoot allowed
        else:
            current_gain = release_coef * current_gain + (1 - release_coef) * needed
        current_gain = min(current_gain, 1.0)
        gain_blocks[i] = current_gain

    gain = np.repeat(gain_blocks, block)[:audio.shape[1]]
    limited = audio * gain[np.newaxis, :]
    # final hard safety clip, just in case (guarantees ceiling regardless of block resolution)
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


# ---------------------------------------------------------------------------
# Time-based effects -- short reverb & slapback delay (lead vocal ambience)
# ---------------------------------------------------------------------------
# Yeh naya block block-recurrence trick istemal karta hai (jaise upar
# envelope_follower aur apply_limiter mein already hota hai) taaki lambi
# feedback-delay wale comb/allpass filters bhi Render jaise free-tier CPU
# par slow/timeout na ho -- ek per-sample Python loop ki jagah, exactly
# delay-length ke blocks mein vectorized numpy recursion chalti hai.

def _comb_filter_block(x: np.ndarray, delay_samples: int, feedback: float) -> np.ndarray:
    """Feedback comb filter: y[n] = x[n] + feedback * y[n - delay_samples]."""
    n = x.shape[0]
    y = np.empty(n)
    prev_block = np.zeros(delay_samples)
    pos = 0
    while pos < n:
        end = min(pos + delay_samples, n)
        cur_len = end - pos
        y[pos:end] = x[pos:end] + feedback * prev_block[:cur_len]
        prev_block = y[pos:end] if cur_len == delay_samples else np.pad(y[pos:end], (0, delay_samples - cur_len))
        pos = end
    return y

def _allpass_filter_block(x: np.ndarray, delay_samples: int, feedback: float) -> np.ndarray:
    """Schroeder allpass filter: y[n] = -feedback*x[n] + x[n-D] + feedback*y[n-D]."""
    n = x.shape[0]
    y = np.empty(n)
    prev_x_block = np.zeros(delay_samples)
    prev_y_block = np.zeros(delay_samples)
    pos = 0
    while pos < n:
        end = min(pos + delay_samples, n)
        cur_len = end - pos
        cur_x = x[pos:end]
        y[pos:end] = -feedback * cur_x + prev_x_block[:cur_len] + feedback * prev_y_block[:cur_len]
        prev_x_block = cur_x if cur_len == delay_samples else np.pad(cur_x, (0, delay_samples - cur_len))
        prev_y_block = y[pos:end] if cur_len == delay_samples else np.pad(y[pos:end], (0, delay_samples - cur_len))
        pos = end
    return y

def apply_short_reverb(audio: np.ndarray, sr: int, wet_mix: float = 0.14, room_size_ms: float = 45.0) -> np.ndarray:
    """
    Halka short plate/room reverb -- Schroeder-style network (4 parallel
    feedback comb filters + 2 series allpass filters for diffusion), chhoti
    decay time (~0.3-0.5s). Maqsad sirf itna space/depth dena hai ki vocal
    "khaali" na lage, bina use peeche dhakelne ke -- isliye wet_mix jaan-
    boojh kar low rakha gaya hai (vocal hamesha dry-dominant, upfront
    rehta hai).
    """
    comb_delays_ms = [29.7, 37.1, 41.1, 43.7]
    comb_gains = [0.74, 0.73, 0.715, 0.697]
    allpass_delays_ms = [5.0, 1.7]
    allpass_gain = 0.6
    scale = max(room_size_ms, 5.0) / 43.7

    out = np.empty_like(audio)
    for ch in range(audio.shape[0]):
        x = audio[ch]
        tail = np.zeros_like(x)
        for d_ms, g in zip(comb_delays_ms, comb_gains):
            d_samples = max(1, int(sr * d_ms * scale / 1000.0))
            tail = tail + _comb_filter_block(x, d_samples, g)
        tail = tail / len(comb_delays_ms)
        for d_ms in allpass_delays_ms:
            d_samples = max(1, int(sr * d_ms / 1000.0))
            tail = _allpass_filter_block(tail, d_samples, allpass_gain)
        out[ch] = x + wet_mix * tail
    return out

def apply_slapback_delay(audio: np.ndarray, sr: int, delay_ms: float = 110.0,
                          feedback: float = 0.16, wet_mix: float = 0.15) -> np.ndarray:
    """
    Halka slapback delay: ek chhota single/double echo, low feedback aur low
    wet_mix ke saath, taaki vocal mein thoda "bounce"/space feel ho lekin
    saaf-suthri, upfront vocal clarity kharab na ho.
    """
    delay_samples = max(1, int(sr * delay_ms / 1000.0))
    out = np.empty_like(audio)
    for ch in range(audio.shape[0]):
        x = audio[ch]
        y = _comb_filter_block(x, delay_samples, feedback)
        wet_only = y - x  # sirf delayed echoes; dry hamesha 100% level par rehta hai
        out[ch] = x + wet_mix * wet_only
    return out

def apply_presence_boost(audio: np.ndarray, sr: int, gain_db: float = 2.5) -> np.ndarray:
    """
    Upper-mid 'presence' boost (~3-8kHz) -- vocal mein chamak/clarity ke
    liye, jaisa professional Bollywood playback vocals mein hota hai. Ek
    wide bell band jo roughly 3-8kHz range ko halka boost karta hai.
    """
    return apply_eq_band(audio, sr, freq_hz=5200.0, gain_db=gain_db, q=0.75, filter_type="bell")
