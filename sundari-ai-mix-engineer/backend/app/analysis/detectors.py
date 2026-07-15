"""
detectors.py
============
Higher-level heuristic detectors: bass balance and vocal presence.

Honest technical note on "Instrument Separation" (requested in the spec):
True source separation (splitting a finished stereo mix back into
vocal/drums/bass/other stems) is NOT something that can be done reliably
with spectral heuristics or classic DSP — it genuinely requires a trained
deep neural network. There is no shortcut around this; any DSP-only
"separation" would produce unusable, artifact-heavy results and would be
misleading to ship as a real feature.

The correct, honest path (documented here and to be wired up in a later
phase) is to integrate an existing open-source, pretrained separation
model such as:
  - Demucs (Meta AI, MIT licensed) - state of the art, runs locally,
    GPU-accelerated, no cloud dependency required.
  - Spleeter (Deezer, MIT licensed) - lighter weight, faster, slightly
    lower quality than Demucs.
Both are free/open-source and match the spec's "prefer free & open source"
instruction. This module therefore exposes a clean `SeparationBackend`
interface now (Phase 1) so Phase 4 (Auto-Fix) and later phases can plug in
Demucs without re-architecting the analysis engine, but does not fake a
DSP-only separation result.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from .spectral import band_energy_db, _to_mono


@dataclass
class BassBalanceResult:
    sub_bass_db: float
    bass_db: float
    balance_status: str  # "boomy" | "thin" | "balanced"
    sub_to_bass_ratio_db: float


def analyze_bass_balance(audio: np.ndarray, sr: int) -> BassBalanceResult:
    bands = band_energy_db(audio, sr)
    sub = bands["sub_bass"] if bands["sub_bass"] is not None else -80.0
    bass = bands["bass"] if bands["bass"] is not None else -80.0
    ratio = round(sub - bass, 2)

    if ratio >= 4:
        status = "boomy"       # too much sub relative to punchy bass region
    elif ratio <= -6:
        status = "thin"        # bass region present but no low-end foundation
    else:
        status = "balanced"

    return BassBalanceResult(
        sub_bass_db=sub, bass_db=bass,
        balance_status=status, sub_to_bass_ratio_db=ratio,
    )


@dataclass
class VocalPresenceResult:
    presence_score: float  # 0-100, heuristic
    status: str  # "buried" | "recessed" | "balanced" | "forward"
    vocal_band_db: float
    context_band_db: float


def analyze_vocal_presence(
    vocal_track: np.ndarray, full_mix: np.ndarray, sr: int,
) -> VocalPresenceResult:
    """
    Heuristic proxy for "is the vocal sitting forward or buried in the
    mix", using the vocal fundamental+presence range (~1kHz-5kHz, where
    human vocal intelligibility concentrates) compared against the same
    band's energy in the full mix minus the vocal.

    This requires the isolated vocal stem to be provided separately (as
    per the spec's "analyze each track separately"). If only a full mix
    is available with no separated vocal stem, true per-instrument
    presence cannot be measured without source separation (see the module
    docstring above re: Demucs integration).
    """
    vocal_bands = band_energy_db(vocal_track, sr)
    mix_bands = band_energy_db(full_mix, sr)

    vocal_presence_band = np.nanmean([
        vocal_bands["mid"], vocal_bands["upper_mid"]
    ])
    mix_presence_band = np.nanmean([
        mix_bands["mid"], mix_bands["upper_mid"]
    ])

    gap = vocal_presence_band - mix_presence_band
    # Map gap (roughly -12dB..+6dB) onto a 0-100 presence score
    score = float(np.clip((gap + 12) / 18 * 100, 0, 100))

    if score < 25:
        status = "buried"
    elif score < 45:
        status = "recessed"
    elif score < 75:
        status = "balanced"
    else:
        status = "forward"

    return VocalPresenceResult(
        presence_score=round(score, 1),
        status=status,
        vocal_band_db=round(float(vocal_presence_band), 2),
        context_band_db=round(float(mix_presence_band), 2),
    )


class SeparationBackend:
    """
    Interface placeholder for source separation, to be implemented in a
    later phase using Demucs (preferred, GPU-accelerated, MIT license) or
    Spleeter as a lighter-weight fallback. Deliberately raises rather than
    returning fake/silent results, so calling code never mistakes an
    unimplemented feature for a working one.
    """

    def separate(self, audio: np.ndarray, sr: int) -> dict:
        raise NotImplementedError(
            "Instrument separation requires a trained neural model "
            "(Demucs/Spleeter) which will be integrated in a later phase. "
            "Until then, please upload separated stems (vocal, drums, bass, "
            "other) directly for full per-instrument analysis."
        )
