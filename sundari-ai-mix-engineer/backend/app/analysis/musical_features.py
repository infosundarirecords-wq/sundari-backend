"""
musical_features.py
====================
Spec ke items ⑦ BPM, ⑧ Musical Key, ⑥ Genre, ⑨ Mood ke liye.

Honest breakdown of what's actually DSP-solvable vs. what needs ML:

- **BPM (Tempo)**: Genuinely solvable with classical DSP — onset detection
  + autocorrelation/comb-filter tempo estimation. Implemented here for
  real using onset envelope + autocorrelation (no external ML model
  needed).

- **Musical Key**: Genuinely solvable with classical DSP — chroma
  (pitch-class) feature extraction + correlation against the well-known
  Krumhansl-Schmuckler key profiles. Implemented here for real.

- **Genre**: This is NOT reliably solvable with plain DSP/heuristics.
  Genre is a cultural/stylistic category, not a physical property of the
  waveform — two songs with near-identical spectral/rhythmic features can
  be different genres, and genre boundaries are fuzzy even for humans.
  Reliable genre detection needs a model trained on labeled genre data
  (e.g. a pretrained audio classifier such as Essentia's Discogs-EffNet
  genre model, or passing extracted features + a short audio description
  to a multimodal LLM). We extract objective descriptive features here
  (tempo, spectral centroid/brightness, dynamic character, rhythmic
  density) and hand them to the Decision Engine's LLM layer as
  *context*, where the LLM can offer a qualitative, explained guess —
  but we do not claim a hard "genre classifier" here, because a
  DSP-only one would not be honest or accurate.

- **Mood**: Same limitation as Genre, arguably even more subjective.
  Same approach: extract objective descriptive features (tempo, key
  mode major/minor, dynamic range, spectral brightness) and let the
  Decision Engine's LLM reason about likely mood qualitatively, clearly
  presented as an interpretation, not a measurement.
"""

from __future__ import annotations

import numpy as np
from scipy import signal
from dataclasses import dataclass, asdict


def _to_mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio
    return np.mean(audio, axis=0)


# ---------------------------------------------------------------------------
# BPM Detection
# ---------------------------------------------------------------------------

@dataclass
class TempoResult:
    bpm: float
    confidence: float  # 0-1, autocorrelation peak ki sharpness ke aadhar par


def detect_bpm(audio: np.ndarray, sr: int) -> TempoResult:
    """
    Onset-envelope + autocorrelation based tempo estimation:
      1. Signal ko spectral-flux se onset strength envelope mein convert
         karte hain (jahan naye transients/beats hote hain, wahan spike
         aati hai).
      2. Us envelope ka autocorrelation nikalte hain — agar beat har X
         seconds mein repeat ho rahi hai, to autocorrelation lag=X par
         ek strong peak dikhayega.
      3. 60-200 BPM ke musically-plausible range mein sabse strong peak
         choose karte hain.
    """
    mono = _to_mono(audio)

    # Downsample onset envelope computation ke liye (speed ke liye; tempo
    # detection ko full sample rate resolution ki zaroorat nahi hoti)
    hop_length = 512
    frame_length = 2048

    n_frames = 1 + (len(mono) - frame_length) // hop_length
    if n_frames <= 1:
        return TempoResult(bpm=0.0, confidence=0.0)

    # Spectral flux onset envelope
    stft_frames = np.abs(np.array([
        np.fft.rfft(mono[i * hop_length: i * hop_length + frame_length] *
                     np.hanning(frame_length))
        for i in range(n_frames)
    ]))
    flux = np.sqrt(np.sum(np.diff(stft_frames, axis=0).clip(min=0) ** 2, axis=1))
    flux = np.concatenate([[0], flux])

    frame_rate = sr / hop_length  # frames per second

    # Autocorrelation of the onset envelope
    flux = flux - np.mean(flux)
    autocorr = np.correlate(flux, flux, mode="full")
    autocorr = autocorr[len(autocorr) // 2:]

    min_bpm, max_bpm = 60, 200
    min_lag = int(frame_rate * 60 / max_bpm)
    max_lag = min(int(frame_rate * 60 / min_bpm), len(autocorr) - 1)

    if max_lag <= min_lag:
        return TempoResult(bpm=0.0, confidence=0.0)

    search_region = autocorr[min_lag:max_lag]
    if len(search_region) == 0 or np.max(np.abs(search_region)) == 0:
        return TempoResult(bpm=0.0, confidence=0.0)

    peak_idx = int(np.argmax(search_region)) + min_lag
    bpm = 60.0 * frame_rate / peak_idx

    peak_value = autocorr[peak_idx]
    mean_value = np.mean(np.abs(search_region))
    confidence = float(np.clip(peak_value / (mean_value * 5 + 1e-9), 0, 1)) if mean_value > 0 else 0.0

    return TempoResult(bpm=round(bpm, 1), confidence=round(confidence, 3))


# ---------------------------------------------------------------------------
# Musical Key Detection (Krumhansl-Schmuckler)
# ---------------------------------------------------------------------------

# Krumhansl-Kessler key profiles — music-perception research se derived
# probe-tone ratings, jo batati hain ki har pitch-class ek diye gaye key
# mein kitni "sthir" (stable/fitting) lagti hai.
_MAJOR_PROFILE = np.array([
    6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88,
])
_MINOR_PROFILE = np.array([
    6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17,
])

_PITCH_CLASSES = [
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
]


@dataclass
class KeyResult:
    key: str          # e.g. "C Major", "A Minor"
    tonic: str
    mode: str          # "Major" | "Minor"
    confidence: float  # 0-1, best correlation match ki relative strength


def _chroma_vector(mono: np.ndarray, sr: int) -> np.ndarray:
    """
    Simple chroma (pitch-class) feature: STFT bins ko unki nearest musical
    pitch (MIDI note) ke through 12 pitch-classes mein fold karte hain,
    aur unki energy sum karte hain.
    """
    n_fft = 4096
    hop = 2048
    n_frames = max(1, (len(mono) - n_fft) // hop)

    chroma_sum = np.zeros(12)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)

    # Freq -> pitch class mapping (ek baar precompute)
    with np.errstate(divide="ignore"):
        midi = 69 + 12 * np.log2(np.maximum(freqs, 1e-6) / 440.0)
    pitch_class = np.round(midi).astype(int) % 12
    valid = (freqs > 50) & (freqs < 5000)  # musically relevant range

    for i in range(n_frames):
        frame = mono[i * hop: i * hop + n_fft]
        if len(frame) < n_fft:
            break
        spectrum = np.abs(np.fft.rfft(frame * np.hanning(n_fft)))
        for pc in range(12):
            mask = valid & (pitch_class == pc)
            if np.any(mask):
                chroma_sum[pc] += np.sum(spectrum[mask] ** 2)

    total = np.sum(chroma_sum)
    if total > 0:
        chroma_sum = chroma_sum / total
    return chroma_sum


def detect_musical_key(audio: np.ndarray, sr: int) -> KeyResult:
    mono = _to_mono(audio)
    chroma = _chroma_vector(mono, sr)

    best_score = -np.inf
    best_tonic = 0
    best_mode = "Major"
    all_scores = []

    for tonic in range(12):
        major_rotated = np.roll(_MAJOR_PROFILE, tonic)
        minor_rotated = np.roll(_MINOR_PROFILE, tonic)

        major_corr = np.corrcoef(chroma, major_rotated)[0, 1]
        minor_corr = np.corrcoef(chroma, minor_rotated)[0, 1]

        all_scores.append(major_corr)
        all_scores.append(minor_corr)

        if major_corr > best_score:
            best_score = major_corr
            best_tonic = tonic
            best_mode = "Major"
        if minor_corr > best_score:
            best_score = minor_corr
            best_tonic = tonic
            best_mode = "Minor"

    all_scores = np.array(all_scores)
    second_best = np.sort(all_scores)[-2] if len(all_scores) > 1 else 0.0
    confidence = float(np.clip((best_score - second_best) * 2, 0, 1))

    tonic_name = _PITCH_CLASSES[best_tonic]
    return KeyResult(
        key=f"{tonic_name} {best_mode}",
        tonic=tonic_name,
        mode=best_mode,
        confidence=round(confidence, 3),
    )


# ---------------------------------------------------------------------------
# Descriptive features for Genre/Mood (LLM context, NOT a classifier)
# ---------------------------------------------------------------------------

@dataclass
class DescriptiveFeatures:
    """
    Yeh Genre/Mood ka 'answer' nahi hai — yeh sirf objective, DSP-measured
    descriptors hain jo Decision Engine ke LLM context mein jaate hain,
    taaki AI apna qualitative, explained assessment de sake (jaise ek
    insaan sunkar bolta hai "yeh energetic/upbeat lagta hai" — based on
    tempo + dynamics + brightness).
    """
    tempo_bpm: float
    key: str
    mode: str  # Major/Minor -> aksar mood perception se loosely correlated
    spectral_brightness_hz: float   # spectral centroid — zyada = "bright", kam = "dark/warm"
    dynamic_range_db: float          # zyada = "dynamic/organic", kam = "compressed/aggressive"
    rhythmic_density: float          # onsets per second — zyada = "busy/energetic"


def extract_descriptive_features(
    audio: np.ndarray, sr: int, tempo: TempoResult, key: KeyResult, dynamic_range_db: float,
) -> DescriptiveFeatures:
    mono = _to_mono(audio)
    freqs, psd = signal.welch(mono, fs=sr, nperseg=min(8192, len(mono)))
    centroid = float(np.sum(freqs * psd) / max(np.sum(psd), 1e-12))

    # Rhythmic density (rough proxy): onset count via simple energy-based
    # peak picking on a downsampled envelope.
    hop = 512
    env = np.array([
        np.sqrt(np.mean(mono[i:i + hop] ** 2))
        for i in range(0, len(mono) - hop, hop)
    ])
    if len(env) > 2:
        peaks, _ = signal.find_peaks(env, distance=3, prominence=np.std(env) * 0.5)
        duration_s = len(mono) / sr
        density = len(peaks) / max(duration_s, 1e-6)
    else:
        density = 0.0

    return DescriptiveFeatures(
        tempo_bpm=tempo.bpm,
        key=key.key,
        mode=key.mode,
        spectral_brightness_hz=round(centroid, 1),
        dynamic_range_db=round(dynamic_range_db, 2),
        rhythmic_density=round(float(density), 2),
    )
