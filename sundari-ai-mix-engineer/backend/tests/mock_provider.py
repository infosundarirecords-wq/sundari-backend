"""
mock_provider.py
=================
Sirf testing ke liye — real API call kiye bina Provider Registry, Fallback
Chain, aur Decision Engine ke poore data-flow ko verify karta hai. Yeh
production code ka hissa nahi hai (isliye `app/` folder ke bahar, `tests/`
mein hai), lekin `LLMProvider` interface ko sahi tarah implement karta
hai — isse yeh proof milta hai ki architecture sach mein provider-agnostic
hai (Claude/OpenAI/Gemini/Local LLM ki jagah koi bhi compliant provider
kaam kar sakta hai).
"""

from __future__ import annotations

from app.decision_engine.providers.base import (
    LLMProvider, DecisionRequest, DecisionResponse, ProviderCapability, ProviderError,
)


def _sample_valid_decision_json(track_names: list[str]) -> dict:
    return {
        "iteration_number": 1,
        "genre_detected": "Pop",
        "mood_detected": "Upbeat",
        "bpm_detected": 120.0,
        "musical_key_detected": "C Major",
        "overall_mix_assessment": "Mock provider ka test assessment.",
        "track_decisions": [
            {
                "track_name": name,
                "eq_bands": [
                    {"frequency_hz": 350, "gain_db": -3.0, "q_factor": 1.4,
                     "filter_type": "bell", "dynamic": False},
                ],
                "compression": {
                    "needed": True, "threshold_db": -18.0, "ratio": 3.0,
                    "attack_ms": 15.0, "release_ms": 120.0, "makeup_gain_db": 3.0,
                    "multiband": False,
                },
                "de_esser": None,
                "saturation": None,
                "stereo": {"width_adjustment_percent": 0.0, "pan_position": 0.0},
                "space_effects": None,
                "sidechain": None,
                "clip_gain_adjustment_db": 0.0,
                "automation": [],
                "teaching_explanation": {
                    "what_was_the_problem": "Mock problem",
                    "why_it_was_a_problem": "Mock why",
                    "what_was_changed": "Mock change",
                    "why_this_change": "Mock reasoning",
                    "expected_difference": "Mock difference",
                    "what_if_not_fixed": "Mock consequence",
                    "professional_reasoning": "Mock professional tip",
                },
                "confidence": 0.85,
            }
            for name in track_names
        ],
        "master_decision": None,
        "ready_for_mastering": False,
        "remaining_issues": ["Mock remaining issue"],
    }


class MockProvider(LLMProvider):
    """Hamesha ek valid, schema-compliant response deta hai."""

    @property
    def capabilities(self) -> set[ProviderCapability]:
        return {ProviderCapability.STRUCTURED_OUTPUT}

    async def generate_decision(self, request: DecisionRequest) -> DecisionResponse:
        track_names = [t["track_name"] for t in request.mix_context_json.get("tracks", [])]
        return DecisionResponse(
            decision_json=_sample_valid_decision_json(track_names or ["Unknown Track"]),
            reasoning_text="Mock reasoning text.",
            provider_name="mock",
            model_name="mock-model-v1",
            input_tokens=100,
            output_tokens=200,
            estimated_cost_usd=0.001,
        )

    async def health_check(self) -> bool:
        return True


class AlwaysFailProvider(LLMProvider):
    """Fallback-chain logic test karne ke liye — hamesha retryable error deta hai."""

    @property
    def capabilities(self) -> set[ProviderCapability]:
        return set()

    async def generate_decision(self, request: DecisionRequest) -> DecisionResponse:
        raise ProviderError("always_fail", "Yeh provider jaanbujhkar hamesha fail hota hai.", retryable=True)

    async def health_check(self) -> bool:
        return False


class InvalidSchemaProvider(LLMProvider):
    """Schema-validation test karne ke liye — jaanbujhkar incomplete JSON deta hai."""

    @property
    def capabilities(self) -> set[ProviderCapability]:
        return set()

    async def generate_decision(self, request: DecisionRequest) -> DecisionResponse:
        return DecisionResponse(
            decision_json={"iteration_number": 1},  # required fields missing
            reasoning_text="Invalid response",
            provider_name="invalid_schema",
            model_name="invalid-model",
        )

    async def health_check(self) -> bool:
        return True
