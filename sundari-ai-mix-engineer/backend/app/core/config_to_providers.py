"""
config_to_providers.py
=======================
`app/core/config.py` ki Settings se `ProviderConfig` objects ki ordered
list banata hai, jo `ProviderChain` ko diya jaata hai. Yeh dono modules
(config aur decision_engine) ke beech ka connecting piece hai — config
sirf raw settings (env vars) jaanta hai, decision_engine sirf
ProviderConfig jaanta hai, yeh function beech mein translate karta hai.
"""

from __future__ import annotations

from app.core.config import Settings
from app.decision_engine.providers.base import ProviderConfig


def build_provider_configs(settings: Settings) -> list[ProviderConfig]:
    all_configs = {
        "claude": ProviderConfig(
            provider_name="claude",
            model_name=settings.anthropic_model,
            api_key=settings.anthropic_api_key or None,
        ),
        "openai": ProviderConfig(
            provider_name="openai",
            model_name=settings.openai_model,
            api_key=settings.openai_api_key or None,
        ),
        "gemini": ProviderConfig(
            provider_name="gemini",
            model_name=settings.gemini_model,
            api_key=settings.gemini_api_key or None,
        ),
        "local_llm": ProviderConfig(
            provider_name="local_llm",
            model_name=settings.local_llm_model,
            base_url=settings.local_llm_base_url,
        ),
    }

    ordered = []
    for name in settings.decision_provider_order:
        name = name.strip()
        if name in all_configs:
            ordered.append(all_configs[name])
    return ordered
