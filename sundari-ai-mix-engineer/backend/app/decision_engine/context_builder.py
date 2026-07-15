"""
context_builder.py
===================
Poore project ka analysis data (Phase 1 numeric metrics, Phase 2 rule-based
findings, musical features) leta hai aur ek structured `DecisionRequest`
banata hai jo kisi bhi LLMProvider ko bheja ja sake.

Yeh module khud koi "decision" nahi leta — yeh sirf context ko is tarah
organize karta hai ki AI (Claude/OpenAI/Gemini/Local LLM) ke paas
professional engineer ke barabar jaankari ho: har track ke numbers, unka
aapas mein sambandh (masking conflicts), aur poore project ka musical
context (genre-context features, BPM, key, mood-context features).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from app.decision_engine.providers.base import DecisionRequest
from app.decision_engine.decision_schema import build_json_schema_for_prompt


SYSTEM_CONTEXT_TEMPLATE = """\
Aap ek anubhavi (experienced) Professional Mixing aur Mastering Engineer hain, \
jinka naam Sundari AI hai. Aapko ek pura music project diya jaa raha hai — \
saare tracks ke numeric analysis (loudness, dynamics, spectral balance, \
stereo image), unke aapas ke sambandh (jaise frequency masking), aur \
project ka musical context (tempo, key, mood-descriptive features).

Aapke kaam karne ka tareeka:

1. Koi bhi fixed preset ya generic "template" mat use kijiye. Har project \
alag hai — is specific gaane ke genre, mood, tempo, aur har track ke \
actual numbers ke hisaab se sochiye, na ki kisi standard formula se.

2. Har track ko individually samjhiye, lekin decisions lete waqt hamesha \
poore mix ka context dhyan mein rakhiye — jaise agar Kick aur Bass clash \
kar rahe hain, to dono ke decisions ek doosre se related honge.

3. Har decision ke saath poori teaching explanation dijiye: samasya kya \
thi, kyun thi, aapne kya badla, kyun badla, isse kya antar aayega, agar \
na badalte to kya samasya rehti, aur professional engineers is tarah ke \
maamle mein aam taur par kya sochte hain.

4. Apna confidence score honestly dijiye — agar data ambiguous hai ya \
aap kisi cheez ke baare mein poori tarah sure nahi hain, to confidence \
kam rakhiye, jhooth-moot ka high confidence mat dikhaiye.

5. Genre aur Mood ke baare mein jo bhi kahiye, use clearly ek "sunkar/data \
dekhkar interpretation" ke roop mein present kijiye, ek pakka fact ki \
tarah nahi — kyunki yeh objectively measure nahi kiye ja sakte.

6. Apna poora jawab neeche diye gaye JSON schema ke exact structure mein \
dijiye. Koi extra prose schema ke bahar mat likhiye.
"""


def _findings_summary(track_report) -> list[dict]:
    """Phase 2 ke findings ko compact summary mein convert karta hai."""
    return [
        {
            "id": f.id,
            "severity": f.severity,
            "title": f.title,
            "measured_values": f.measured_values,
        }
        for f in track_report.findings
    ]


def build_track_context(analysis_result, track_report, role: str) -> dict:
    """
    Ek single track ka context dict — Phase 1 ke numeric measurements +
    Phase 2 ke rule-based findings (yeh findings LLM ke liye ek "reference
    point" ki tarah kaam karte hain, fixed instruction ki tarah nahi — LLM
    inhe dekh kar apna khud ka nirnay lega, jo inse match bhi ho sakta hai
    aur alag bhi, agar poore mix ka context kuch aur kahe).
    """
    return {
        "track_name": analysis_result.track_name,
        "role": role,
        "measurements": {
            "integrated_lufs": analysis_result.integrated_lufs,
            "peak_dbfs": analysis_result.peak_dbfs,
            "true_peak_dbtp": analysis_result.true_peak_dbtp,
            "rms_dbfs": analysis_result.rms_dbfs,
            "crest_factor_db": analysis_result.crest_factor_db,
            "dr_value": analysis_result.dr_value,
            "clipping_detected": analysis_result.clipping_detected,
            "stereo_correlation": analysis_result.stereo_correlation,
            "stereo_width_percent": analysis_result.stereo_width_percent,
            "mono_compatibility_risk": analysis_result.mono_compatibility_risk,
            "band_energy_db": analysis_result.band_energy_db,
            "mud_severity": analysis_result.mud_severity,
            "harshness_severity": analysis_result.harshness_severity,
            "sibilance_severity": analysis_result.sibilance_severity,
            "bass_balance_status": analysis_result.bass_balance_status,
        },
        "rule_based_reference_findings": _findings_summary(track_report),
    }


def build_project_context(
    track_contexts: list[dict],
    masking_conflicts: list[dict],
    descriptive_features: Optional[dict] = None,
    iteration_number: int = 1,
    previous_iteration_summary: Optional[str] = None,
) -> dict:
    """
    Poore project ka top-level context — spec ke Iterative AI Mixing
    Engine section ke mutabiq, agar yeh pehli iteration nahi hai, to
    `previous_iteration_summary` bhi bheja jaata hai taaki AI ko pata ho
    ki pichli baar kya decide kiya gaya tha aur ab kya dobara check karna
    hai.
    """
    context = {
        "iteration_number": iteration_number,
        "tracks": track_contexts,
        "masking_conflicts_between_tracks": masking_conflicts,
    }
    if descriptive_features:
        context["musical_context"] = descriptive_features
    if previous_iteration_summary:
        context["previous_iteration_summary"] = previous_iteration_summary
    return context


def build_decision_request(
    project_context: dict, task_description: str = "Poore project ka mixing decision dijiye",
) -> DecisionRequest:
    return DecisionRequest(
        system_context=SYSTEM_CONTEXT_TEMPLATE,
        mix_context_json=project_context,
        output_schema=build_json_schema_for_prompt(),
        task_description=task_description,
    )
