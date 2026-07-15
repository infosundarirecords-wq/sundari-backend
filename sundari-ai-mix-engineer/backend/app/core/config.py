"""
config.py
=========
Centralized application settings, loaded from environment variables (with
sensible local-dev defaults) using pydantic-settings. Keeping this in one
place now (Phase 1) means later phases (auth, cloud sync, subscriptions)
just add fields here rather than scattering `os.environ` calls through
the codebase.
"""

from __future__ import annotations
import os
from functools import lru_cache

try:
    from pydantic_settings import BaseSettings
    from pydantic import Field, field_validator
except ImportError:
    from pydantic import BaseSettings, Field, field_validator  # type: ignore


class Settings(BaseSettings):
    app_name: str = "Sundari AI Mix Engineer"
    environment: str = os.getenv("SUNDARI_ENV", "development")
    api_v1_prefix: str = "/api/v1"

    database_url: str = os.getenv(
        "DATABASE_URL", "sqlite:///./sundari_dev.db"
    )

    max_upload_size_mb: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "500"))
    allowed_audio_extensions: tuple = (".wav", ".mp3", ".aiff", ".aif", ".flac")

    allowed_origins: list = Field(default_factory=list)

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_allowed_origins(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    upload_dir: str = os.getenv("UPLOAD_DIR", "./data/uploads")
    temp_dir: str = os.getenv("TEMP_DIR", "./data/temp")

    decision_provider_order: list = Field(
        default_factory=lambda: os.getenv(
            "DECISION_PROVIDER_ORDER", "claude,openai,gemini,local_llm",
        ).split(",")
    )

    @field_validator("decision_provider_order", mode="before")
    @classmethod
    def _split_provider_order(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5")

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")

    local_llm_base_url: str = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434")
    local_llm_model: str = os.getenv("LOCAL_LLM_MODEL", "llama3.1")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
