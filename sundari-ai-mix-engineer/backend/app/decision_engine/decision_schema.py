"""
decision_schema.py
===================
Yeh define karta hai ki Decision Engine, AI provider (Claude/OpenAI/
Gemini/Local LLM) se kis structure mein jawab maangta hai. Spec ke
"Intelligent Decision Engine" section ke har parameter (EQ, Compression,
Threshold, Ratio, Attack, Release, Makeup Gain, Saturation, Stereo Width,
Reverb, Delay, Limiter, Panning, Automation, Sidechain, Dynamic EQ,
Multiband Compression, De-Esser, Clip Gain) yahan represent hote hain.

Important: yeh sirf numbers nahi maangta — spec ke "AI Teacher" section ke
mutabiq har decision ke saath yeh bhi maanga jaata hai:
  - समस्या क्या थी (what_was_the_problem)
  - क्यों थी (why_it_was_a_problem)
  - क्या बदला (what_was_changed)
  - क्यों बदला (why_this_change)
  - इससे क्या अंतर आया (expected_difference)
  - अगर न करते तो (what_if_not_fixed)
  - Professional Engineer ऐसा क्यों करते हैं (professional_reasoning)

Yeh saat fields Pydantic level par hi required hain — agar koi provider
inhe nahi deta, response validation fail hoga (chup-chaap incomplete
"teaching" wala response accept nahi hoga).
"""

from __future__ import annotations

from typing import Optional, Literal
from pydantic import BaseModel, Field


class EQBandDecision(BaseModel):
    frequency_hz: float
    gain_db: float
    q_factor: float
    filter_type: Literal[
        "bell", "high_shelf", "low_shelf", "high_pass", "low_pass", "notch",
    ]
    dynamic: bool = Field(
        False, description="True agar yeh EQ band dynamic honi chahiye (sirf tab active ho jab zaroorat ho)",
    )


class CompressionDecision(BaseModel):
    needed: bool
    threshold_db: Optional[float] = None
    ratio: Optional[float] = None
    attack_ms: Optional[float] = None
    release_ms: Optional[float] = None
    makeup_gain_db: Optional[float] = None
    multiband: bool = False
    multiband_bands: Optional[list[dict]] = None  # agar multiband True ho


class DeEsserDecision(BaseModel):
    needed: bool
    frequency_range_hz: Optional[list[float]] = None  # [low, high]
    reduction_db: Optional[float] = None


class SaturationDecision(BaseModel):
    needed: bool
    amount_percent: Optional[float] = None
    character: Optional[Literal["tape", "tube", "transistor", "digital"]] = None


class StereoDecision(BaseModel):
    width_adjustment_percent: float = Field(
        0.0, description="0 = koi badlaav nahi, +ve = wide karna, -ve = narrow karna",
    )
    pan_position: float = Field(0.0, ge=-1.0, le=1.0, description="-1 = poori left, +1 = poori right")


class SpaceEffectsDecision(BaseModel):
    reverb_needed: bool = False
    reverb_send_db: Optional[float] = None
    reverb_type: Optional[str] = None
    delay_needed: bool = False
    delay_send_db: Optional[float] = None
    delay_time_ms: Optional[float] = None


class LimiterDecision(BaseModel):
    needed: bool
    ceiling_dbtp: Optional[float] = None
    target_lufs: Optional[float] = None


class SidechainDecision(BaseModel):
    needed: bool
    trigger_track: Optional[str] = None   # e.g. "Kick" agar bass ko duck karna ho
    amount_db: Optional[float] = None


class AutomationPoint(BaseModel):
    time_seconds: float
    parameter: str            # e.g. "volume", "eq_band_2_gain"
    value: float
    reason: str                # Hindi mein, is automation ki wajah


class TeachingExplanation(BaseModel):
    """
    Spec ke 'AI Teacher' section ke saatoin fields — yeh optional nahi
    hain, kyunki teaching-style report Phase 2 mein pehle se chuni gayi
    user preference hai, aur Decision Engine ke liye bhi wahi apply hota
    hai.
    """
    what_was_the_problem: str
    why_it_was_a_problem: str
    what_was_changed: str
    why_this_change: str
    expected_difference: str
    what_if_not_fixed: str
    professional_reasoning: str


class TrackMixDecision(BaseModel):
    """
    Ek single track ke liye poora decision set — is Decision Engine ka
    core output unit. `TeachingExplanation` har major decision (EQ,
    Compression, waghera) ke saath judi hoti hai.
    """
    track_name: str
    eq_bands: list[EQBandDecision] = Field(default_factory=list)
    compression: CompressionDecision
    de_esser: Optional[DeEsserDecision] = None
    saturation: Optional[SaturationDecision] = None
    stereo: Optional[StereoDecision] = None
    space_effects: Optional[SpaceEffectsDecision] = None
    sidechain: Optional[SidechainDecision] = None
    clip_gain_adjustment_db: float = 0.0
    automation: list[AutomationPoint] = Field(default_factory=list)
    teaching_explanation: TeachingExplanation
    confidence: float = Field(..., ge=0.0, le=1.0, description="AI ka apne decision par confidence score")


class MasterMixDecision(BaseModel):
    limiter: LimiterDecision
    tonal_balance_adjustments: list[EQBandDecision] = Field(default_factory=list)
    target_platform: Optional[str] = None
    teaching_explanation: TeachingExplanation


class ProjectMixDecision(BaseModel):
    """
    Poore project ka top-level response — spec ke '① Project Open karega'
    se le kar '⑤ Poore Mix ka Analysis karega' tak jo bhi hota hai, uska
    final output. `iteration_number` isliye hai kyunki spec ke
    'Iterative AI Mixing Engine' section ke mutabiq yeh ek hi baar nahi,
    baar-baar chal sakta hai jab tak mix professional quality na ho
    jaaye — dekhein iterative_engine.py.
    """
    iteration_number: int
    genre_detected: Optional[str] = None
    mood_detected: Optional[str] = None
    bpm_detected: Optional[float] = None
    musical_key_detected: Optional[str] = None
    overall_mix_assessment: str
    track_decisions: list[TrackMixDecision]
    master_decision: Optional[MasterMixDecision] = None
    ready_for_mastering: bool = Field(
        False, description="AI ka nirnay: kya mix ab professional-quality hai, ya aur iteration chahiye",
    )
    remaining_issues: list[str] = Field(default_factory=list)


def build_json_schema_for_prompt() -> dict:
    """
    Provider ko bheje jaane wale output_schema ke roop mein
    ProjectMixDecision.model_json_schema() istemal hota hai — isse har
    provider (chahe woh native structured-output support kare ya na kare)
    ko exact expected format pata chal jaata hai.
    """
    return ProjectMixDecision.model_json_schema()
