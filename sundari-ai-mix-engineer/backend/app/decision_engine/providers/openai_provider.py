"""
openai_provider.py
===================
OpenAI ke liye LLMProvider implementation. OpenAI ka Structured Outputs
feature (`response_format={"type": "json_schema", ...}`) istemal karte
hain — yeh Claude ke tool-use jaisa hi guarantee deta hai ki response
exactly humare schema se match karega.
"""

from __future__ import annotations

import json

from app.decision_engine.providers.base import (
    LLMProvider, ProviderConfig, DecisionRequest, DecisionResponse,
    ProviderCapability, ProviderError,
)

_OPENAI_PRICING_PER_MILLION_TOKENS = {
    "gpt-5": {"input": 5.0, "output": 15.0},
    "gpt-5-mini": {"input": 0.5, "output": 2.0},
}


class OpenAIProvider(LLMProvider):
    @property
    def capabilities(self) -> set[ProviderCapability]:
        return {ProviderCapability.STRUCTURED_OUTPUT, ProviderCapability.VISION}

    def _client(self):
        try:
            import openai
        except ImportError as e:
            raise ProviderError(
                "openai", "openai package install nahi hai. `pip install openai` chalayein.",
            ) from e
        if not self.config.api_key:
            raise ProviderError("openai", "OPENAI_API_KEY set nahi hai.")
        return openai.OpenAI(api_key=self.config.api_key, timeout=self.config.timeout_seconds)

    async def generate_decision(self, request: DecisionRequest) -> DecisionResponse:
        client = self._client()

        user_content = (
            f"{request.task_description}\n\n"
            f"Project context (JSON):\n{json.dumps(request.mix_context_json, ensure_ascii=False, indent=2)}"
        )

        try:
            response = client.chat.completions.create(
                model=self.config.model_name,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                messages=[
                    {"role": "system", "content": request.system_context},
                    {"role": "user", "content": user_content},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "project_mix_decision",
                        "schema": request.output_schema,
                        "strict": True,
                    },
                },
            )
        except Exception as e:
            retryable = "rate_limit" in str(e).lower() or "timeout" in str(e).lower()
            raise ProviderError("openai", str(e), retryable=retryable) from e

        message = response.choices[0].message
        try:
            decision_json = json.loads(message.content)
        except (json.JSONDecodeError, TypeError) as e:
            raise ProviderError("openai", f"Response JSON parse nahi hui: {e}") from e

        usage = response.usage
        pricing = _OPENAI_PRICING_PER_MILLION_TOKENS.get(self.config.model_name)
        cost = None
        if pricing and usage:
            cost = (
                usage.prompt_tokens * pricing["input"] +
                usage.completion_tokens * pricing["output"]
            ) / 1_000_000

        return DecisionResponse(
            decision_json=decision_json,
            reasoning_text=decision_json.get("overall_mix_assessment", ""),
            provider_name="openai",
            model_name=self.config.model_name,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
            estimated_cost_usd=round(cost, 6) if cost is not None else None,
            raw_provider_response=str(response),
        )

    async def health_check(self) -> bool:
        try:
            client = self._client()
            client.chat.completions.create(
                model=self.config.model_name, max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False
