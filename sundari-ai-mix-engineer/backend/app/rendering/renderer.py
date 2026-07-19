"""
renderer.py
===========
Decision Engine ke ProjectMixDecision (decision_schema.py) ko leke,
har track par actual DSP (dsp.py) apply karta hai, sabko mixdown karta
hai, aur master bus processing (EQ + limiter + LUFS) laga ke final
stereo WAV numpy array deta hai.

Yeh JUCE plugin ke real-time signal chain ka offline/batch Python
equivalent hai — website ke "upload -> final mixed download" flow ke
liye zaroori tha, kyunki plugin sirf Logic Pro ke andar chalta hai.

Lead vocal ambience (v1.1): "lead_vocal" role wale track par, chain ke
end mein (saturation ke baad, clip-gain se pehle) automatically ek
halka presence boost (~3-8kHz) + short plate/room reverb + slapback
delay lagaya jaata hai — fixed, tasteful default settings ke saath,
Decision Engine ke output par depend kiye bina, taaki har project mein
consistently professional/Bollywood-style vocal chamak aur depth mile,
bina vocal ko peeche dhakele.

Jaan-boojh kar scope se bahar rakha gaya (v1): sidechain ducking,
multiband compression, time-based automation, aur per-track AI-decided
reverb/delay amounts (decision_schema.py ke SpaceEffectsDecision field
abhi render mein pass-through nahi hote — sirf lead vocal ka fixed
default chalta hai). Inke decision fields already schema mein maujood
hain, future version mein yahan implement kiye ja sakte hain.
"""

from __future__ import annotations

import numpy as np

from app.rendering import dsp
from app.analysis.metrics import measure_lufs

def render_track(samples: np.ndarray, sr: int, decision: dict, role: str | None = None) -> np.ndarray:
    """Ek track ke liye poori DSP chain: EQ -> De-esser -> Compression ->
    Saturation -> [Lead Vocal: Presence + Reverb + Delay] -> Clip Gain ->
    Stereo/Pan. Returns (2, n_samples) stereo."""
    audio = samples.astype(np.float64)

    eq_bands = decision.get("eq_bands") or []
    if eq_bands:
        audio = dsp.apply_eq_chain(audio, sr, eq_bands)

    de_esser = decision.get("de_esser")
    if de_esser and de_esser.get("needed") and de_esser.get("frequency_range_hz"):
        lo, hi = de_esser["frequency_range_hz"]
        audio = dsp.apply_deesser(audio, sr, lo, hi, de_esser.get("reduction_db") or 3.0)

    compression = decision.get("compression") or {}
    if compression.get("needed"):
        audio = dsp.apply_compressor(
            audio, sr,
            threshold_db=compression.get("threshold_db") if compression.get("threshold_db") is not None else -18.0,
            ratio=compression.get("ratio") or 2.0,
            attack_ms=compression.get("attack_ms") or 10.0,
            release_ms=compression.get("release_ms") or 100.0,
            makeup_gain_db=compression.get("makeup_gain_db") or 0.0,
        )

    saturation = decision.get("saturation")
    if saturation and saturation.get("needed"):
        audio = dsp.apply_saturation(audio, saturation.get("amount_percent") or 10.0)

    # --- Lead vocal ambience: hamesha automatic, har project ke liye ---
    # Fixed, subtle defaults (low wet_mix) taaki vocal hamesha saaf aur
    # sabse aage sunayi de — sirf itna space/chamak ke vocal "khaali" na
    # lage, professional Bollywood playback jaisa touch.
    if role == "lead_vocal":
        audio = dsp.apply_presence_boost(audio, sr, gain_db=2.5)
        audio = dsp.apply_short_reverb(audio, sr, wet_mix=0.14, room_size_ms=45.0)
        audio = dsp.apply_slapback_delay(audio, sr, delay_ms=110.0, feedback=0.16, wet_mix=0.15)

    clip_gain = decision.get("clip_gain_adjustment_db") or 0.0
    audio = dsp.apply_clip_gain(audio, clip_gain)

    stereo = dsp.to_stereo(audio)
    stereo_decision = decision.get("stereo")
    if stereo_decision:
        width = stereo_decision.get("width_adjustment_percent") or 0.0
        pan = stereo_decision.get("pan_position") or 0.0
        if abs(width) > 0.5:
            stereo = dsp.apply_stereo_width(stereo, width)
        if abs(pan) > 0.02:
            stereo = dsp.apply_pan(stereo, pan)

    return stereo

def _pad_to_length(audio: np.ndarray, length: int) -> np.ndarray:
    if audio.shape[1] >= length:
        return audio[:, :length]
    pad = np.zeros((audio.shape[0], length - audio.shape[1]))
    return np.hstack([audio, pad])

def render_project(tracks: list[tuple], project_decision: dict, sr: int) -> np.ndarray:
    """
    tracks: list of (samples: np.ndarray, track_name: str, role: str | None)
    in the same order as project_decision['track_decisions']. role ka
    istemal sirf lead-vocal ambience (presence/reverb/delay) auto-apply
    karne ke liye hota hai — DSP decision khud role-agnostic rehta hai.
    project_decision: ProjectMixDecision.model_dump() output.
    sr: common sample rate (caller ensures all tracks match, ya yahan
    resample kar chuka hota hai).

    Returns: (2, n_samples) final mastered stereo mix, float64, roughly
    [-1, 1] range (already peak-safe via limiter).
    """
    track_decisions = {td["track_name"]: td for td in project_decision.get("track_decisions", [])}

    rendered = []
    max_len = 0
    for track in tracks:
        samples, name, role = track if len(track) == 3 else (*track, None)
        decision = track_decisions.get(name, {})
        stereo = render_track(samples, sr, decision, role=role)
        rendered.append(stereo)
        max_len = max(max_len, stereo.shape[1])

    if not rendered:
        raise ValueError("Koi track render karne ke liye nahi mila.")

    mix = np.zeros((2, max_len))
    for stereo in rendered:
        mix += _pad_to_length(stereo, max_len)

    # Simple headroom gain-stage before master processing, taaki summing se clip na ho
    n_tracks = max(len(rendered), 1)
    mix = mix / np.sqrt(n_tracks)

    master_decision = project_decision.get("master_decision") or {}

    tonal_bands = master_decision.get("tonal_balance_adjustments") or []
    if tonal_bands:
        mix = dsp.apply_eq_chain(mix, sr, tonal_bands)

    limiter = master_decision.get("limiter") or {}
    target_lufs = limiter.get("target_lufs")
    if target_lufs is not None:
        mix = dsp.match_lufs(mix, sr, target_lufs, measure_lufs)

    ceiling = limiter.get("ceiling_dbtp") if limiter.get("needed") else None
    if ceiling is None:
        ceiling = -1.0  # safe default ceiling agar AI ne limiter na maanga ho
    mix = dsp.apply_limiter(mix, ceiling, sr=sr)

    return mix
