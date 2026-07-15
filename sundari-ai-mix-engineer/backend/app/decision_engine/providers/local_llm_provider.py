"""
local_llm_provider.py
======================
Local LLM (Ollama ya kisi bhi OpenAI-compatible local server) ke liye
LLMProvider implementation. Yeh spec ke "Local AI" future-architecture
item ko poora karta hai — bina kisi cloud API key ke, poori tarah user
ke apne machine par chal sakta hai (privacy + zero API cost, lekin
model quality local hardware par depend karti hai).

Honest note: chhote local models (7B-13B jaise) structured JSON output
utni reliably follow nahi karte jitna Claude/GPT-5/Gemini jaise bade
hosted models karte hain. Isliye yeh provider zyada defensive hai —
JSON extraction ke liye regex fallback bhi rakha gaya hai, aur agar
parsing fail ho to clear ProviderError deta hai (chup-chaap galat/adhoori
JSON accept nahi karta).
"""

from __future__ import annotations

import json
import re

from app.decision_engine.providers.base import (
    LLMProvider, DecisionRequest, DecisionResponse,
    ProviderCapability, ProviderError,
)


class LocalLLMProvider(LLMProvider):
    """
    Default base_url Ollama ka standard local endpoint hai
    (http://localhost:11434). Kisi doosre OpenAI-compatible local server
    (jaise LM Studio, vLLM) ke liye `config.base_url` override kiya ja
    sakta hai.
    """

    @property
    def capabilities(self) -> set[ProviderCapability]:
        # STRUCTURED_OUTPUT jaanbujhkar list mein nahi hai — Ollama ka
        # `format: json` mode "valid JSON" guarantee karta hai, lekin
        # humare exact Pydantic schema ka guarantee nahi (jaisa Claude
        # tool-use ya OpenAI json_schema strict mode deta hai). Isliye
        # Decision Engine ko pata hona chahiye ki iska output extra
        # validation maangta hai.
        return set()

    def _base_url(self) -> str:
        return self.config.base_url or "http://localhost:11434"

    async def generate_decision(self, request: DecisionRequest) -> DecisionResponse:
        try:
            import httpx
        except ImportError as e:
            raise ProviderError(
                "local_llm", "httpx package install nahi hai. `pip install httpx` chalayein.",
            ) from e

        prompt = (
            f"{request.system_context}\n\n"
            f"{request.task_description}\n\n"
            f"Project context (JSON):\n"
            f"{json.dumps(request.mix_context_json, ensure_ascii=False, indent=2)}\n\n"
            f"IMPORTANT: Apna poora jawab sirf JSON format mein dijiye, is exact "
            f"schema ke mutabiq (koi extra text schema ke bahar mat likhiye):\n"
            f"{json.dumps(request.output_schema, indent=2)}"
        )

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                response = await client.post(
                    f"{self._base_url()}/api/generate",
                    json={
                        "model": self.config.model_name,
                        "prompt": prompt,
                        "format": "json",
                        "stream": False,
                        "options": {"temperature": self.config.temperature},
                    },
                )
                response.raise_for_status()
                result = response.json()
        except Exception as e:
            raise ProviderError("local_llm", str(e), retryable=True) from e

        raw_text = result.get("response", "")
        decision_json = self._extract_json(raw_text)

        return DecisionResponse(
            decision_json=decision_json,
            reasoning_text=decision_json.get("overall_mix_assessment", ""),
            provider_name="local_llm",
            model_name=self.config.model_name,
            input_tokens=result.get("prompt_eval_count"),
            output_tokens=result.get("eval_count"),
            estimated_cost_usd=0.0,  # Local model -> koi API cost nahi
            raw_provider_response=raw_text,
        )

    def _extract_json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Fallback: chhote local models kabhi-kabhi JSON ke aage-peeche
        # extra commentary de dete hain, isliye pehla {...} block dhoondte hain.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as e:
                raise ProviderError(
                    "local_llm", f"Model se mili JSON invalid hai: {e}",
                ) from e
        raise ProviderError("local_llm", "Response mein koi valid JSON nahi mili.")

    async def health_check(self) -> bool:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self._base_url()}/api/tags")
                return response.status_code == 200
        except Exception:
            return False
