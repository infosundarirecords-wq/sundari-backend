"""
config.py
=========
Centralized application settings, loaded from environment variables (with
sensible local-dev defaults) using pydantic-settings.
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

    allowed_origins_raw: str = os.getenv("ALLOWED_ORIGINS", "")

    @property
    def allowed_origins(self) -> list:
        return [o.strip() for o in self.allowed_origins_raw.split(",") if o.strip()]

    upload_dir: str = os.getenv("UPLOAD_DIR", "./data/uploads")
    temp_dir: str = os.getenv("TEMP_DIR", "./data/temp")

    decision_provider_order_raw: str = os.getenv(
        "DECISION_PROVIDER_ORDER", "claude,openai,gemini,local_llm"
    )

    @property
    def decision_provider_order(self) -> list:
        return [item.strip() for item in self.decision_provider_order_raw.split(",") if item.strip()]

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
