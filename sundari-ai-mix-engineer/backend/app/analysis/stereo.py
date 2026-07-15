"""
stereo.py
=========
Stereo image analysis: correlation (phase), stereo width, and mono
compatibility checks.

Why these specific measures:
- Phase correlation (-1 to +1) is the industry-standard way engineers check
  "will this collapse or cancel in mono?" A correlation meter reading near
  -1 signals real mono-compatibility problems (common with wide stereo
  effects, mid-side over-processing, or out-of-phase mic pairs).
- Stereo width is derived from the mid/side energy ratio, which is how
  most stereo imaging plugins (e.g. iZotope Ozone Imager, Waves S1) define
  and display "width" internally.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass


@dataclass
class StereoResult:
    is_mono: bool
    correlation: float
    width_percent: float
    mono_compatibility_risk: str  # "low" | "medium" | "high"
    left_rms_dbfs: float
    right_rms_dbfs: float
    balance_bias: float  # -1.0 (full left) .. +1.0 (full right)


def _db(value: float, floor_db: float = -120.0) -> float:
    if value <= 0:
        return floor_db
    return max(20.0 * np.log10(value), floor_db)


def analyze_stereo(audio: np.ndarray) -> StereoResult:
    """
    `audio` expected shaped (channels, samples). Mono input is handled
    gracefully by returning neutral/"not applicable" stereo values.
    """
    if audio.ndim == 1 or audio.shape[0] == 1:
        mono = audio if audio.ndim == 1 else audio[0]
        rms = _db(np.sqrt(np.mean(mono ** 2)))
        return StereoResult(
            is_mono=True,
            correlation=1.0,
            width_percent=0.0,
            mono_compatibility_risk="low",
            left_rms_dbfs=rms,
            right_rms_dbfs=rms,
            balance_bias=0.0,
        )

    left = audio[0]
    right = audio[1]

    # Phase correlation coefficient
    if np.std(left) > 0 and np.std(right) > 0:
        correlation = float(np.corrcoef(left, right)[0, 1])
    else:
        correlation = 1.0

    # Mid/Side decomposition for width measurement
    mid = (left + right) / 2.0
    side = (left - right) / 2.0

    mid_power = np.mean(mid ** 2)
    side_power = np.mean(side ** 2)

    if mid_power + side_power > 0:
        width_percent = round(100.0 * side_power / (mid_power + side_power) * 2, 2)
    else:
        width_percent = 0.0
    width_percent = min(width_percent, 200.0)

    if correlation < -0.3:
        risk = "high"
    elif correlation < 0.3:
        risk = "medium"
    else:
        risk = "low"

    left_rms = _db(np.sqrt(np.mean(left ** 2)))
    right_rms = _db(np.sqrt(np.mean(right ** 2)))

    # Balance bias: relative energy difference, normalized -1..+1
    l_lin = np.sqrt(np.mean(left ** 2))
    r_lin = np.sqrt(np.mean(right ** 2))
    total = l_lin + r_lin
    balance_bias = round(float((r_lin - l_lin) / total), 3) if total > 0 else 0.0

    return StereoResult(
        is_mono=False,
        correlation=round(correlation, 3),
        width_percent=width_percent,
        mono_compatibility_risk=risk,
        left_rms_dbfs=round(left_rms, 2),
        right_rms_dbfs=round(right_rms, 2),
        balance_bias=balance_bias,
    )
