"""
provider_registry.py
=====================
Yeh module do zimmedariyaan nibhaata hai:

1. **Factory**: provider name (string, jaise "claude" ya "openai") se
   sahi `LLMProvider` subclass ka instance banata hai. Naya provider
   future mein add karna sirf `_PROVIDER_CLASSES` dict mein ek line
   add karna hai — kahin aur koi if/else change nahi karna padta.

2. **Fallback Chain**: agar primary provider fail ho jaaye (rate limit,
   downtime, invalid API key), to registry automatically config mein
   diye gaye fallback order ke agle provider ko try karta hai. Yeh spec
   ke "bhavishya mein aane wale kisi bhi AI Model ke saath kaam kar sake"
   requirement ko production-safe banata hai — agar ek provider down ho,
   poora Decision Engine down nahi hota.
"""

from __future__ import annotations

from app.decision_engine.providers.base import (
    LLMProvider, ProviderConfig, DecisionRequest, DecisionResponse, ProviderError,
)
from app.decision_engine.providers.claude_provider import ClaudeProvider
from app.decision_engine.providers.openai_provider import OpenAIProvider
from app.decision_engine.providers.gemini_provider import GeminiProvider
from app.decision_engine.providers.local_llm_provider import LocalLLMProvider


_PROVIDER_CLASSES: dict[str, type[LLMProvider]] = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "local_llm": LocalLLMProvider,
}


def register_provider(name: str, provider_class: type[LLMProvider]) -> None:
    """
    Bhavishya mein koi naya AI model/provider aane par, koi bhi is
    function ko call karke use registry mein add kar sakta hai — bina
    is file ke andar kuch edit kiye. (Jaise ek naya `providers/xyz_provider.py`
    likh kar `register_provider("xyz", XYZProvider)` call karna.)
    """
    _PROVIDER_CLASSES[name] = provider_class


def create_provider(config: ProviderConfig) -> LLMProvider:
    provider_class = _PROVIDER_CLASSES.get(config.provider_name)
    if provider_class is None:
        raise ProviderError(
            config.provider_name,
            f"Provider '{config.provider_name}' registered nahi hai. "
            f"Available: {list(_PROVIDER_CLASSES.keys())}",
        )
    return provider_class(config)


class ProviderChain:
    """
    Configs ki ek ordered list leta hai (jaise [Claude, OpenAI, Gemini]),
    aur `generate_decision()` call hone par pehle provider se try karta
    hai; agar woh `ProviderError(retryable=True)` de, to chain ke agle
    provider par move karta hai. Agar koi bhi provider kaam na kare, to
    saari errors collect karke ek combined ProviderError raise karta hai.
    """

    def __init__(self, configs: list[ProviderConfig]):
        if not configs:
            raise ValueError("ProviderChain ke liye kam se kam ek config zaroori hai.")
        self.configs = configs

    async def generate_decision(self, request: DecisionRequest) -> DecisionResponse:
        errors: list[str] = []
        for config in self.configs:
            provider = create_provider(config)
            try:
                return await provider.generate_decision(request)
            except ProviderError as e:
                errors.append(str(e))
                if not e.retryable:
                    # Non-retryable error (jaise invalid schema, auth
                    # config galat) — is provider ko dobara try karne ka
                    # koi fayda nahi, lekin chain ke agle provider ko
                    # zaroor try karte hain (ho sakta hai sirf isी
                    # provider mein problem ho).
                    continue
                continue
        raise ProviderError(
            "provider_chain",
            f"Saare providers fail ho gaye. Errors: {'; '.join(errors)}",
        )
