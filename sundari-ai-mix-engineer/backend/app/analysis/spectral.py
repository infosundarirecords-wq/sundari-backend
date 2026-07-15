"""
spectral.py
===========
Frequency-domain analysis: full spectrum computation, band-energy
extraction, and heuristic detection of common mix problems (mud,
harshness, sibilance) plus frequency masking between two tracks.

Design notes / honest limitations:
- "Mud", "harshness", and "sibilance" are not physically-defined
  quantities — they are perceptual/engineering terms. We operationalize
  them the same way a mix engineer would explain them to a student:
    * Mud      -> excess energy in ~200-500 Hz relative to the rest of the
                   spectrum (boxy, undefined low-mid buildup).
    * Harshness-> excess energy in ~2-5 kHz relative to neighboring bands
                   (fatiguing upper-mid resonance).
    * Sibilance-> excess energy specifically in ~5-9 kHz concentrated in
                   short bursts (correlates with "S"/"T" consonants in
                   vocals), detected via short-time energy spikes in that
                   band rather than just average energy.
  These thresholds are configurable and should be tuned against a labeled
  reference set in a later phase (Phase 2/3 will add the AI report layer
  that turns these numeric flags into plain-language explanations).
- Frequency masking detection compares two tracks' band energies to flag
  where two sources compete for the same frequency range at similar
  levels (e.g. kick vs. bass), which is a genuine, well-understood mixing
  problem (frequency/simultaneous masking, per psychoacoustic masking
  theory), not something available "for free" from any single library.
"""

from __future__ import annotations

import numpy as np
from scipy import signal
from dataclasses import dataclass, field


# Standard mixing-relevant frequency bands (Hz)
BANDS = {
    "sub_bass": (20, 60),
    "bass": (60, 250),
    "low_mid": (250, 500),
    "mid": (500, 2000),
    "upper_mid": (2000, 4000),
    "presence": (4000, 6000),
    "brilliance": (6000, 20000),
}


def _to_mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio
    return np.mean(audio, axis=0)


def compute_spectrum(audio: np.ndarray, sr: int, n_fft: int = 8192):
    """
    Returns (frequencies, magnitude_db) for the averaged power spectrum of
    the whole file, computed via Welch's method (averaged periodograms)
    for a smoother, more representative spectrum than a single raw FFT.
    """
    mono = _to_mono(audio)
    nperseg = min(n_fft, len(mono))
    freqs, psd = signal.welch(mono, fs=sr, nperseg=nperseg, scaling="spectrum")
    magnitude_db = 10 * np.log10(np.maximum(psd, 1e-12))
    return freqs, magnitude_db


def band_energy_db(audio: np.ndarray, sr: int) -> dict:
    """
    Average energy (dB, relative) in each standard mixing band.

    IMPORTANT: averaging must happen in the LINEAR POWER domain, then be
    converted to dB once at the end — NOT by averaging already-computed
    dB values bin-by-bin. A wide band (e.g. upper_mid spans 2000-4000Hz,
    hundreds of FFT bins) will contain mostly noise-floor bins and only a
    few bins carrying a dominant tone/formant; averaging in the dB domain
    lets those silent bins wash out the real energy (dB is already
    logarithmic, so "averaging logs" is not the same as "averaging power"
    and badly underestimates energy concentrated in a few bins). Averaging
    linear power first, then taking 10*log10 of that mean, correctly
    reflects the true energy contained in the band.
    """
    mono = _to_mono(audio)
    nperseg = min(8192, len(mono))
    freqs, psd = signal.welch(mono, fs=sr, nperseg=nperseg, scaling="spectrum")

    result = {}
    for name, (lo, hi) in BANDS.items():
        mask = (freqs >= lo) & (freqs < hi)
        if np.any(mask):
            mean_power = np.mean(psd[mask])
            result[name] = round(float(10 * np.log10(max(mean_power, 1e-12))), 2)
        else:
            result[name] = None
    return result


@dataclass
class MudResult:
    detected: bool
    severity: str  # "none" | "mild" | "moderate" | "severe"
    low_mid_db: float
    relative_excess_db: float


def detect_mud(audio: np.ndarray, sr: int) -> MudResult:
    bands = band_energy_db(audio, sr)
    low_mid = bands["low_mid"]
    reference = np.nanmean([
        v for k, v in bands.items()
        if k in ("bass", "mid") and v is not None
    ])
    excess = round(low_mid - reference, 2) if low_mid is not None else 0.0

    if excess >= 6:
        severity = "severe"
    elif excess >= 3:
        severity = "moderate"
    elif excess >= 1.5:
        severity = "mild"
    else:
        severity = "none"

    return MudResult(
        detected=severity != "none",
        severity=severity,
        low_mid_db=low_mid if low_mid is not None else 0.0,
        relative_excess_db=excess,
    )


@dataclass
class HarshnessResult:
    detected: bool
    severity: str
    upper_mid_db: float
    relative_excess_db: float


def detect_harshness(audio: np.ndarray, sr: int) -> HarshnessResult:
    bands = band_energy_db(audio, sr)
    upper_mid = bands["upper_mid"]
    reference = np.nanmean([
        v for k, v in bands.items()
        if k in ("mid", "presence") and v is not None
    ])
    excess = round(upper_mid - reference, 2) if upper_mid is not None else 0.0

    if excess >= 6:
        severity = "severe"
    elif excess >= 3:
        severity = "moderate"
    elif excess >= 1.5:
        severity = "mild"
    else:
        severity = "none"

    return HarshnessResult(
        detected=severity != "none",
        severity=severity,
        upper_mid_db=upper_mid if upper_mid is not None else 0.0,
        relative_excess_db=excess,
    )


@dataclass
class SibilanceResult:
    detected: bool
    severity: str
    peak_count_per_10s: float
    band_db: float


def detect_sibilance(audio: np.ndarray, sr: int, frame_ms: float = 20.0) -> SibilanceResult:
    """
    Sibilance is bursty by nature (it rides on "s"/"sh"/"t" consonants),
    so unlike mud/harshness we look at short-time energy spikes in the
    5-9kHz band rather than a single averaged level.
    """
    mono = _to_mono(audio)
    sos = signal.butter(4, [5000, 9000], btype="bandpass", fs=sr, output="sos")
    band_signal = signal.sosfilt(sos, mono)

    frame_len = max(int(sr * frame_ms / 1000), 1)
    n_frames = len(band_signal) // frame_len
    if n_frames == 0:
        return SibilanceResult(False, "none", 0.0, -120.0)

    frame_energy = np.array([
        np.sqrt(np.mean(band_signal[i * frame_len:(i + 1) * frame_len] ** 2))
        for i in range(n_frames)
    ])
    frame_db = 20 * np.log10(np.maximum(frame_energy, 1e-9))

    overall_band_db = round(float(np.mean(frame_db)), 2)
    threshold = np.mean(frame_db) + 6.0  # spikes 6dB+ above the band's own average
    spike_count = int(np.sum(frame_db > threshold))

    duration_s = len(mono) / sr
    peaks_per_10s = round(spike_count / max(duration_s, 1e-6) * 10, 2)

    if peaks_per_10s >= 15:
        severity = "severe"
    elif peaks_per_10s >= 8:
        severity = "moderate"
    elif peaks_per_10s >= 3:
        severity = "mild"
    else:
        severity = "none"

    return SibilanceResult(
        detected=severity != "none",
        severity=severity,
        peak_count_per_10s=peaks_per_10s,
        band_db=overall_band_db,
    )


@dataclass
class MaskingConflict:
    band: str
    track_a_db: float
    track_b_db: float
    level_gap_db: float
    severity: str


def detect_frequency_masking(
    audio_a: np.ndarray, audio_b: np.ndarray, sr: int,
    conflict_threshold_db: float = 3.0,
) -> list:
    """
    Compares band energies between two tracks (e.g. kick vs bass, lead
    vocal vs rhythm guitar) and flags bands where both are loud AND close
    in level (small gap = neither clearly "wins" -> masking / competing for
    the same space). A large energy gap in a shared band is NOT flagged,
    since one source clearly sits in front there by design.
    """
    bands_a = band_energy_db(audio_a, sr)
    bands_b = band_energy_db(audio_b, sr)

    conflicts = []
    for band in BANDS:
        a_val = bands_a.get(band)
        b_val = bands_b.get(band)
        if a_val is None or b_val is None:
            continue
        gap = abs(a_val - b_val)
        # Only a concern if both are relatively energetic in this band
        both_present = a_val > -40 and b_val > -40
        if both_present and gap <= conflict_threshold_db:
            if gap <= 1.0:
                severity = "severe"
            elif gap <= 2.0:
                severity = "moderate"
            else:
                severity = "mild"
            conflicts.append(MaskingConflict(
                band=band, track_a_db=a_val, track_b_db=b_val,
                level_gap_db=round(gap, 2), severity=severity,
            ))
    return conflicts
