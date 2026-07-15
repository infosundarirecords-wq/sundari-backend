"""
gemini_provider.py
===================
Google Gemini ke liye LLMProvider implementation. Gemini ka structured
output `response_schema` + `response_mime_type="application/json"` se
milta hai.
"""

from __future__ import annotations

import json

from app.decision_engine.providers.base import (
    LLMProvider, DecisionRequest, DecisionResponse,
    ProviderCapability, ProviderError,
)


class GeminiProvider(LLMProvider):
    @property
    def capabilities(self) -> set[ProviderCapability]:
        return {ProviderCapability.STRUCTURED_OUTPUT, ProviderCapability.LONG_CONTEXT}

    def _client(self):
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise ProviderError(
                "gemini", "google-generativeai package install nahi hai. "
                "`pip install google-generativeai` chalayein.",
            ) from e
        if not self.config.api_key:
            raise ProviderError("gemini", "GEMINI_API_KEY set nahi hai.")
        genai.configure(api_key=self.config.api_key)
        return genai

    async def generate_decision(self, request: DecisionRequest) -> DecisionResponse:
        genai = self._client()

        user_content = (
            f"{request.task_description}\n\n"
            f"Project context (JSON):\n{json.dumps(request.mix_context_json, ensure_ascii=False, indent=2)}"
        )

        try:
            model = genai.GenerativeModel(
                model_name=self.config.model_name,
                system_instruction=request.system_context,
            )
            response = model.generate_content(
                user_content,
                generation_config=genai.types.GenerationConfig(
                    temperature=self.config.temperature,
                    max_output_tokens=self.config.max_tokens,
                    response_mime_type="application/json",
                    response_schema=request.output_schema,
                ),
            )
        except Exception as e:
            retryable = "resource_exhausted" in str(e).lower() or "429" in str(e)
            raise ProviderError("gemini", str(e), retryable=retryable) from e

        try:
            decision_json = json.loads(response.text)
        except (json.JSONDecodeError, AttributeError) as e:
            raise ProviderError("gemini", f"Response JSON parse nahi hui: {e}") from e

        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", None) if usage else None
        output_tokens = getattr(usage, "candidates_token_count", None) if usage else None

        return DecisionResponse(
            decision_json=decision_json,
            reasoning_text=decision_json.get("overall_mix_assessment", ""),
            provider_name="gemini",
            model_name=self.config.model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=None,  # Gemini pricing tier-dependent hai; Phase 9 mein cost-tracking config se add hoga
            raw_provider_response=str(response),
        )

    async def health_check(self) -> bool:
        try:
            genai = self._client()
            model = genai.GenerativeModel(model_name=self.config.model_name)
            model.generate_content("ping", generation_config={"max_output_tokens": 1})
            return True
        except Exception:
            return False
