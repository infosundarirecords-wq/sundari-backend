"""
engine.py
=========
Decision Engine ka top-level orchestrator. Yeh:
  1. Context Builder se poora project context banata hai.
  2. Provider Chain (Claude -> OpenAI -> Gemini -> Local LLM, config se
     tay order) ko call karta hai.
  3. Response ko `ProjectMixDecision` Pydantic model se validate karta hai
     — agar AI ne schema todkar kuch bheja, yahin fail hoga (chup-chaap
     invalid data aage nahi jaayega).
"""

from __future__ import annotations

from pydantic import ValidationError

from app.decision_engine.providers.base import ProviderConfig, ProviderError
from app.decision_engine.provider_registry import ProviderChain
from app.decision_engine.decision_schema import ProjectMixDecision
from app.decision_engine.context_builder import (
    build_track_context, build_project_context, build_decision_request,
)


class DecisionEngineError(Exception):
    pass


class DecisionEngine:
    def __init__(self, provider_configs: list[ProviderConfig]):
        self.chain = ProviderChain(provider_configs)

    async def decide(
        self,
        track_analyses: list,       # list of (TrackAnalysisResult, TrackReport, role)
        masking_conflicts: list,
        descriptive_features: dict | None = None,
        iteration_number: int = 1,
        previous_iteration_summary: str | None = None,
    ) -> ProjectMixDecision:
        track_contexts = [
            build_track_context(result, report, role)
            for (result, report, role) in track_analyses
        ]
        project_context = build_project_context(
            track_contexts, masking_conflicts, descriptive_features,
            iteration_number, previous_iteration_summary,
        )
        request = build_decision_request(project_context)

        try:
            response = await self.chain.generate_decision(request)
        except ProviderError as e:
            raise DecisionEngineError(f"Decision Engine fail ho gaya: {e}") from e

        try:
            decision = ProjectMixDecision.model_validate(response.decision_json)
        except ValidationError as e:
            raise DecisionEngineError(
                f"AI provider ({response.provider_name}) ne schema-invalid response diya: {e}",
            ) from e

        return decision
