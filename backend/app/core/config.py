"""Application settings loaded from environment variables (.env supported)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "SupportFlow AI"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False

    database_url: str = "postgresql+psycopg://supportflow:supportflow@localhost:5432/supportflow"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-in-production-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 7

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    frontend_url: str = "http://localhost:5173"
    public_api_url: str = "http://localhost:8000"

    # PayPal
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_webhook_id: str = ""
    paypal_timeout_seconds: float = 20.0

    # LLM provider abstraction
    llm_provider: Literal["openai", "gemini", "none"] = "none"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    gemini_api_key: str = ""
    # Express-mode / Vertex AI keys: set true to use the Vertex AI endpoint instead of the Gemini Developer API.
    gemini_use_vertexai: bool = False
    # Gemini Developer API version. v1beta serves every current model and the *-latest aliases; v1 does not.
    gemini_api_version: str = "v1beta"
    # Tried when the main model errors or times out (e.g. 404, 504 DEADLINE_EXCEEDED). Empty disables it.
    gemini_fallback_model: str = "gemini-2.5-flash"
    gemini_model: str = "gemini-flash-latest"
    gemini_embedding_model: str = "models/gemini-embedding-001"
    embedding_dimensions: int = 768
    llm_timeout_seconds: float = 60.0

    # AG Studio licence (frontend reads VITE_AG_LICENSE_KEY; backend only reports presence)
    ag_license_key: str = Field(default="", alias="VITE_AG_LICENSE_KEY")

    # Demo
    demo_currency: str = "USD"

    upload_dir: str = "uploads"
    max_upload_mb: int = 10
    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 10

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, v: str) -> str:
        # Hosted Postgres (Render, Railway, Neon...) hands out postgres:// or postgresql:// URLs.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def paypal_configured(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_client_secret)

    @property
    def paypal_webhook_configured(self) -> bool:
        return self.paypal_configured and bool(self.paypal_webhook_id)

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        if self.llm_provider == "gemini":
            return bool(self.gemini_api_key)
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
