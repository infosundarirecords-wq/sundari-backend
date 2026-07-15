"""
schemas.py
==========
Pydantic models defining the API's request/response contracts. Kept
separate from the analysis engine's internal dataclasses so the API
contract can evolve (versioning, optional fields, docs) without touching
core DSP code.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class TrackAnalysisResponse(BaseModel):
    track_name: str
    duration_seconds: float
    sample_rate: int
    channels: int

    integrated_lufs: float = Field(..., description="ITU-R BS.1770-4 integrated loudness")
    momentary_max_lufs: float
    short_term_max_lufs: float
    loudness_range_lu: float = Field(..., description="Loudness Range in LU")

    peak_dbfs: float
    true_peak_dbtp: float = Field(..., description="Inter-sample true peak (dBTP)")
    rms_dbfs: float

    crest_factor_db: float
    dr_value: float = Field(..., description="Simplified DR-meter-style dynamic range value")

    clipping_detected: bool
    clipped_percentage: float

    is_mono: bool
    stereo_correlation: float = Field(..., ge=-1.0, le=1.0)
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

    class Config:
        json_schema_extra = {
            "example": {
                "track_name": "Lead Vocal",
                "duration_seconds": 210.5,
                "sample_rate": 48000,
                "channels": 2,
                "integrated_lufs": -16.2,
                "momentary_max_lufs": -8.1,
                "short_term_max_lufs": -10.4,
                "loudness_range_lu": 6.3,
                "peak_dbfs": -1.2,
                "true_peak_dbtp": -0.8,
                "rms_dbfs": -18.4,
                "crest_factor_db": 17.2,
                "dr_value": 9.5,
                "clipping_detected": False,
                "clipped_percentage": 0.0,
                "is_mono": False,
                "stereo_correlation": 0.82,
                "stereo_width_percent": 34.5,
                "mono_compatibility_risk": "low",
                "band_energy_db": {"bass": -28.1, "low_mid": -20.4},
                "mud_detected": True,
                "mud_severity": "moderate",
                "harshness_detected": False,
                "harshness_severity": "none",
                "sibilance_detected": True,
                "sibilance_severity": "mild",
                "bass_balance_status": "balanced",
                "sub_to_bass_ratio_db": -1.2,
            }
        }


class MaskingConflictItem(BaseModel):
    band: str
    track_a_db: float
    track_b_db: float
    level_gap_db: float
    severity: str


class MaskingComparisonResponse(BaseModel):
    track_a_name: str
    track_b_name: str
    conflicts: list[MaskingConflictItem]


class VocalPresenceResponse(BaseModel):
    presence_score: float = Field(..., ge=0, le=100)
    status: str
    vocal_band_db: float
    context_band_db: float


class ErrorResponse(BaseModel):
    detail: str


# ---------------------------------------------------------------------------
# Phase 2: AI Mix Report / Learning Mode schemas
# ---------------------------------------------------------------------------

class FindingItem(BaseModel):
    id: str
    category: str
    severity: str = Field(..., description="info | mild | moderate | severe")
    title: str
    why_explanation: str = Field(..., description="Yeh samasya kyun hai")
    how_to_fix: str = Field(..., description="Ise kaise theek karein")
    professional_tip: str = Field(..., description="Professional engineers kya karte hain")
    measured_values: dict = {}


class TrackReportResponse(BaseModel):
    track_name: str
    track_role: str
    overall_status: str = Field(..., description="excellent | good | needs_attention | critical")
    findings: list[FindingItem]
    summary_line: str


class MaskingReportResponse(BaseModel):
    track_a: str
    track_b: str
    title: str
    why_explanation: str
    how_to_fix: str
    professional_tip: str
    conflicting_bands: list[str]
