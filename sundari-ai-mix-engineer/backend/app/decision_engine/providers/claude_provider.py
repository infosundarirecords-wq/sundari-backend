"""
claude_provider.py
===================
Anthropic Claude ke liye LLMProvider implementation. Claude ka structured
output "tool use" ke through hota hai — hum ek single tool define karte
hain jiska input schema hi humara ProjectMixDecision schema hai, aur
`tool_choice` se Claude ko force karte hain ki wahi tool call kare. Isse
hume guaranteed valid-JSON-shaped response milta hai (free-text se JSON
nikaalne ki fragile koshish nahi karni padti).
"""

from __future__ import annotations

import json
import time

from app.decision_engine.providers.base import (
    LLMProvider, ProviderConfig, DecisionRequest, DecisionResponse,
    ProviderCapability, ProviderError,
)

# Anthropic ke pricing (approx, USD per million tokens) — cost estimation
# ke liye. Yeh hardcoded values hain isliye inhe periodically update karna
# zaroori hai (dekhein docs/DEPLOYMENT_GUIDE.md mein cost-tracking note).
_CLAUDE_PRICING_PER_MILLION_TOKENS = {
    "claude-opus-4-8": {"input": 15.0, "output": 75.0},
    "claude-sonnet-5": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.8, "output": 4.0},
}


class ClaudeProvider(LLMProvider):
    @property
    def capabilities(self) -> set[ProviderCapability]:
        return {
            ProviderCapability.STRUCTURED_OUTPUT,
            ProviderCapability.LONG_CONTEXT,
            ProviderCapability.VISION,
        }

    def _client(self):
        try:
            import anthropic
        except ImportError as e:
            raise ProviderError(
                "claude", "anthropic package install nahi hai. "
                "`pip install anthropic` chalayein.",
            ) from e
        if not self.config.api_key:
            raise ProviderError("claude", "ANTHROPIC_API_KEY set nahi hai.")
        return anthropic.Anthropic(api_key=self.config.api_key, timeout=self.config.timeout_seconds)

    async def generate_decision(self, request: DecisionRequest) -> DecisionResponse:
        client = self._client()

        tool_definition = {
            "name": "submit_mixing_decision",
            "description": "Poora project mixing decision, teaching explanation ke saath, submit karo.",
            "input_schema": request.output_schema,
        }

        user_content = (
            f"{request.task_description}\n\n"
            f"Project context (JSON):\n{json.dumps(request.mix_context_json, ensure_ascii=False, indent=2)}"
        )

        try:
            response = client.messages.create(
                model=self.config.model_name,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                system=request.system_context,
                tools=[tool_definition],
                tool_choice={"type": "tool", "name": "submit_mixing_decision"},
                messages=[{"role": "user", "content": user_content}],
            )
        except Exception as e:
            # Anthropic SDK apne specific exceptions throw karta hai
            # (RateLimitError, APIStatusError, waghera) — hum sabko ek
            # common ProviderError mein normalize karte hain taaki
            # Decision Engine ka fallback logic provider-agnostic rahe.
            retryable = "rate_limit" in str(e).lower() or "overloaded" in str(e).lower()
            raise ProviderError("claude", str(e), retryable=retryable) from e

        tool_use_block = next(
            (b for b in response.content if b.type == "tool_use"), None,
        )
        if tool_use_block is None:
            raise ProviderError("claude", "Response mein tool_use block nahi mila.")

        decision_json = tool_use_block.input

        reasoning_text = "\n".join(
            b.text for b in response.content if b.type == "text"
        )

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        pricing = _CLAUDE_PRICING_PER_MILLION_TOKENS.get(self.config.model_name)
        cost = None
        if pricing:
            cost = (
                input_tokens * pricing["input"] + output_tokens * pricing["output"]
            ) / 1_000_000

        return DecisionResponse(
            decision_json=decision_json,
            reasoning_text=reasoning_text,
            provider_name="claude",
            model_name=self.config.model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=round(cost, 6) if cost is not None else None,
            raw_provider_response=str(response),
        )

    async def health_check(self) -> bool:
        try:
            client = self._client()
            client.messages.create(
                model=self.config.model_name, max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False
