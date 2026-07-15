"""
base.py
=======
Multi-Provider Decision Engine ka core contract. Har AI provider (Claude,
OpenAI, Gemini, Local LLM/Ollama, ya bhavishya ka koi bhi naya model) is
`LLMProvider` abstract base class ko implement karta hai — isliye
`decision_engine/engine.py` (jo actual mixing decisions leta hai) ko kabhi
yeh pata karne ki zaroorat nahi ki niche kaunsa specific provider chal raha
hai. Yeh "Strategy Pattern" hai: engine ek interface se baat karta hai,
implementation switch ho sakti hai bina engine ka code chhue.

Design decision: yeh ek structured-output contract hai (JSON schema ke
saath), sirf free-text nahi — kyunki Decision Engine ko machine-readable
parameters (EQ frequency, gain, Q, compressor ratio, waghera) chahiye,
sirf ek paragraph explanation nahi. Har provider implementation ko yeh
zimmedari hai ki woh apne underlying API (chahe woh function-calling ho,
JSON mode ho, ya sirf prompt-engineering se JSON nikalna ho) ko is
structured format mein convert kare.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class ProviderCapability(str, Enum):
    """
    Har provider apni capabilities declare karta hai — isse Decision Engine
    ko pata chalta hai ki koi provider structured JSON output reliably de
    sakta hai ya nahi, aur agar nahi to zyada defensive parsing karni hogi.
    """
    STRUCTURED_OUTPUT = "structured_output"   # native JSON schema / function calling
    STREAMING = "streaming"
    VISION = "vision"                          # spectrogram image samajh sakta hai
    LONG_CONTEXT = "long_context"               # poore mix ka bada context handle kar sakta hai


@dataclass
class ProviderConfig:
    """
    Har provider ki apni configuration — API key, model name, endpoint
    (local providers jaise Ollama ke liye zaroori), timeout, waghera.
    Yeh dataclass provider-agnostic hai; provider-specific extra fields
    `extra` dict mein jaate hain taaki base contract clutter na ho.
    """
    provider_name: str
    model_name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None      # Local LLM (Ollama) ke liye zaroori
    timeout_seconds: int = 60
    max_tokens: int = 4096
    temperature: float = 0.3            # kam temperature -> zyada consistent/deterministic mixing decisions
    extra: dict = field(default_factory=dict)


@dataclass
class DecisionRequest:
    """
    Decision Engine se Provider ko jaane wala request. `system_context`
    mein Sundari ka "professional mixing engineer" persona + rules hote
    hain, `mix_context_json` mein poore project ka structured analysis
    data (Phase 1/2 ka output + genre/BPM/key/mood) hota hai, aur
    `output_schema` mein woh exact JSON structure hoti hai jo response
    mein expected hai (taaki provider implementations ise apne
    structured-output mechanism mein pass kar sakein).
    """
    system_context: str
    mix_context_json: dict
    output_schema: dict
    task_description: str   # e.g. "Lead Vocal ke liye EQ/Compression decide karo"


@dataclass
class DecisionResponse:
    """
    Provider se wapas aane wala response — hamesha isी structure mein,
    chahe underlying provider Claude ho ya Ollama. `raw_provider_response`
    debugging/logging ke liye rakha gaya hai, business logic isko kabhi
    directly use nahi karti.
    """
    decision_json: dict          # parsed, validated structured decision
    reasoning_text: str          # AI ne apni soch kis tarah explain ki (Learning Mode ke liye)
    provider_name: str
    model_name: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    raw_provider_response: Optional[str] = None


class ProviderError(Exception):
    """
    Saare provider-specific errors (auth failure, rate limit, timeout,
    malformed response) is ek common exception type mein normalize hote
    hain, taaki Decision Engine ka fallback-chain logic (agar Claude fail
    ho to OpenAI try karo, waghera) provider-specific exception types par
    depend na kare.
    """
    def __init__(self, provider_name: str, message: str, retryable: bool = False):
        self.provider_name = provider_name
        self.retryable = retryable
        super().__init__(f"[{provider_name}] {message}")


class LLMProvider(ABC):
    """
    Har concrete provider (ClaudeProvider, OpenAIProvider, GeminiProvider,
    LocalLLMProvider) isse inherit karke `generate_decision()` implement
    karta hai. Naya provider add karna is architecture mein sirf ek naya
    file banane jaisa hai — `decision_engine/engine.py` ya API layer mein
    kahin bhi if/else branching nahi karni padti (dekhein provider_registry.py).
    """

    def __init__(self, config: ProviderConfig):
        self.config = config

    @property
    @abstractmethod
    def capabilities(self) -> set[ProviderCapability]:
        ...

    @abstractmethod
    async def generate_decision(self, request: DecisionRequest) -> DecisionResponse:
        """
        Yeh method poore mix/track context ko provider ke API format mein
        convert karta hai, API call karta hai, aur response ko wapas
        DecisionResponse mein normalize karke deta hai.

        Implementations ko yeh zaroor karna chahiye:
        - System context + mix context + output schema ko provider ke
          expected message format mein daalna.
        - Provider-specific errors ko ProviderError mein wrap karna.
        - Agar provider native structured-output support nahi karta
          (jaise kuch local LLMs), to response text se JSON reliably
          extract/validate karna (aur agar parsing fail ho to
          ProviderError raise karna, chup-chaap galat data return nahi
          karna).
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Provider abhi available/reachable hai ya nahi (auth valid hai, endpoint up hai)."""
        ...
