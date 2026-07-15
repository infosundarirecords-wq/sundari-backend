"""
engine.py
=========
AnalysisEngine: the single orchestrator class the API layer calls. It runs
every metric/detector module against a loaded track (or the full mix) and
assembles one structured result object. Phase 2 (AI Mix Report) consumes
this structured output and turns it into plain-language, teachable
findings — this module intentionally stays purely numeric/technical.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, asdict, field
from typing import Optional

from .metrics import (
    measure_lufs, measure_peak_dbfs, measure_true_peak_dbtp,
    measure_rms_dbfs, measure_dynamic_range, detect_clipping,
)
from .stereo import analyze_stereo
from .spectral import (
    compute_spectrum, band_energy_db, detect_mud, detect_harshness,
    detect_sibilance, detect_frequency_masking,
)
from .detectors import analyze_bass_balance, analyze_vocal_presence


@dataclass
class TrackAnalysisResult:
    track_name: str
    duration_seconds: float
    sample_rate: int
    channels: int

    integrated_lufs: float
    momentary_max_lufs: float
    short_term_max_lufs: float
    loudness_range_lu: float

    peak_dbfs: float
    true_peak_dbtp: float
    rms_dbfs: float

    crest_factor_db: float
    dr_value: float

    clipping_detected: bool
    clipped_percentage: float

    is_mono: bool
    stereo_correlation: float
    stereo_width_percent: float
    mono_compatibility_risk: str

    band_energy_db: dict

    mud_detected: bool
    mud_severity: str
    harshness_detected: bool
    harshness_severity: str
    sibilance_detected: bool
    sibilance_severity: str

    bass_balance_status: str
    sub_to_bass_ratio_db: float

    def to_dict(self) -> dict:
        return asdict(self)


class AnalysisEngine:
    """
    Usage:
        engine = AnalysisEngine()
        result = engine.analyze_track(samples, sr, track_name="Lead Vocal")
        conflicts = engine.compare_masking(kick_samples, bass_samples, sr)
    """

    def analyze_track(
        self, samples: np.ndarray, sr: int, track_name: str = "Untitled",
    ) -> TrackAnalysisResult:
        n_channels = 1 if samples.ndim == 1 else samples.shape[0]
        n_samples = samples.shape[-1]
        duration = n_samples / sr

        loudness = measure_lufs(samples, sr)
        peak = measure_peak_dbfs(samples)
        true_peak = measure_true_peak_dbtp(samples, sr)
        rms = measure_rms_dbfs(samples)
        dyn = measure_dynamic_range(samples, sr)
        clipping = detect_clipping(samples)
        stereo = analyze_stereo(samples)
        bands = band_energy_db(samples, sr)
        mud = detect_mud(samples, sr)
        harsh = detect_harshness(samples, sr)
        sib = detect_sibilance(samples, sr)
        bass_bal = analyze_bass_balance(samples, sr)

        return TrackAnalysisResult(
            track_name=track_name,
            duration_seconds=round(duration, 3),
            sample_rate=sr,
            channels=n_channels,
            integrated_lufs=loudness.integrated_lufs,
            momentary_max_lufs=loudness.momentary_max_lufs,
            short_term_max_lufs=loudness.short_term_max_lufs,
            loudness_range_lu=loudness.loudness_range_lu,
            peak_dbfs=peak,
            true_peak_dbtp=true_peak,
            rms_dbfs=rms,
            crest_factor_db=dyn.crest_factor_db,
            dr_value=dyn.dr_value,
            clipping_detected=clipping.is_clipping,
            clipped_percentage=clipping.clipped_percentage,
            is_mono=stereo.is_mono,
            stereo_correlation=stereo.correlation,
            stereo_width_percent=stereo.width_percent,
            mono_compatibility_risk=stereo.mono_compatibility_risk,
            band_energy_db=bands,
            mud_detected=mud.detected,
            mud_severity=mud.severity,
            harshness_detected=harsh.detected,
            harshness_severity=harsh.severity,
            sibilance_detected=sib.detected,
            sibilance_severity=sib.severity,
            bass_balance_status=bass_bal.balance_status,
            sub_to_bass_ratio_db=bass_bal.sub_to_bass_ratio_db,
        )

    def compare_masking(self, samples_a: np.ndarray, samples_b: np.ndarray, sr: int) -> list:
        conflicts = detect_frequency_masking(samples_a, samples_b, sr)
        return [
            {
                "band": c.band, "track_a_db": c.track_a_db,
                "track_b_db": c.track_b_db, "level_gap_db": c.level_gap_db,
                "severity": c.severity,
            }
            for c in conflicts
        ]

    def analyze_vocal_in_mix(
        self, vocal_samples: np.ndarray, mix_samples: np.ndarray, sr: int,
    ) -> dict:
        result = analyze_vocal_presence(vocal_samples, mix_samples, sr)
        return asdict(result)
