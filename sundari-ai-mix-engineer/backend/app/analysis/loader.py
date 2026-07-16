"""
loader.py
=========
Multi-format audio loading (WAV, MP3, AIFF, FLAC).

Strategy:
- Primary path: `soundfile` (libsndfile) handles WAV/AIFF/FLAC natively,
  losslessly, and fast. `librosa.load` is used as the loading front-end
  because it transparently falls back to `audioread`/ffmpeg for MP3 (which
  libsndfile does not support directly), so a single call handles all four
  required formats.
- Output is always normalized to float64 numpy array, shape
  (channels, samples), plus the original sample rate. We deliberately do
  NOT resample by default (mastering/analysis should happen at the
  source sample rate) — resampling is only done inside specific metrics
  (e.g. true-peak oversampling) where it is spec-required.

Requires `ffmpeg` to be installed on the host system for MP3 support
(librosa/audioread shell out to it). This is documented in the
Installation Guide (Phase 1 docs) as a system dependency.
"""

from __future__ import annotations

import os
import numpy as np
from dataclasses import dataclass

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".aiff", ".aif", ".flac"}


@dataclass
class LoadedAudio:
    samples: np.ndarray  # shape (channels, n_samples), float64, range ~[-1, 1]
    sample_rate: int
    channels: int
    duration_seconds: float
    original_path: str


class UnsupportedFormatError(Exception):
    pass


def load_audio(path: str) -> LoadedAudio:
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFormatError(
            f"'{ext}' is not supported. Supported formats: "
            f"{sorted(SUPPORTED_EXTENSIONS)}"
        )

    try:
        import librosa
        # sr=None preserves native sample rate; mono=False keeps channels
        samples, sr = librosa.load(path, sr=None, mono=False)
    except ImportError as e:
        raise ImportError(
            "librosa is required to load audio files. Install project "
            "requirements with: pip install -r requirements.txt "
            "(MP3 support additionally requires ffmpeg on the system PATH)."
        ) from e

    if samples.ndim == 1:
        samples_2d = samples[np.newaxis, :]
    else:
        samples_2d = samples

    n_channels, n_samples = samples_2d.shape
    duration = n_samples / sr

    return LoadedAudio(
        # NOTE: float32 (not float64) — halves memory usage. Multiple full
        # songs loaded together as float64 was almost certainly exceeding
        # Render's free-tier 512MB RAM limit, causing the process to be
        # killed mid-request (which shows up to the browser as a CORS/502
        # error, since the process dies before it can send any response).
        # float32 has ~7 decimal digits precision — plenty for audio
        # (24-bit audio only needs ~144dB dynamic range, float32 covers
        # this easily).
        samples=samples_2d.astype(np.float32),
        sample_rate=int(sr),
        channels=n_channels,
        duration_seconds=round(float(duration), 3),
        original_path=path,
    )
