"""Centralized configuration loaded from environment variables.

All settings are validated by Pydantic. Modules MUST NOT read os.environ directly;
they import `settings` from here. This keeps the env contract auditable.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. Reads `.env` and process env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- General ----------
    app_env: Literal["development", "staging", "production"] = "development"
    app_name: str = "ai-coding-agent"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    # ---------- API ----------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 1
    api_reload: bool = False
    api_cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # ---------- Security ----------
    jwt_secret: str = Field(min_length=16)
    jwt_algorithm: Literal["HS256", "RS256"] = "HS256"
    jwt_access_ttl_min: int = 15
    jwt_refresh_ttl_days: int = 30
    password_hash_scheme: Literal["argon2"] = "argon2"

    # ---------- Seed admin ----------
    seed_admin: bool = False
    seed_admin_email: str = "admin@local.test"
    seed_admin_password: str = "changeme123!"

    # ---------- Postgres ----------
    database_url: PostgresDsn

    # ---------- Redis ----------
    redis_url: RedisDsn

    # ---------- Qdrant (forward-compat, Phase 2+) ----------
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str | None = None

    # ---------- LLM (forward-compat, Phase 4+) ----------
    llm_provider: Literal["ollama", "openai", "vllm", "anthropic"] = "ollama"
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_default_model: str = "llama3.1:8b"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_default_model: str = "gpt-4o-mini"

    # ---------- Embeddings (forward-compat) ----------
    embedding_provider: Literal["local", "openai"] = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # ---------- Rate limits ----------
    rate_limit_anon_per_min: int = 30
    rate_limit_authed_per_min: int = 300
    rate_limit_auth_endpoints_per_min: int = 10

    # ---------- Observability ----------
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "ai-coding-agent-api"
    prometheus_enabled: bool = True

    @field_validator("api_cors_origins", mode="before")
    @classmethod
    def split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def is_prod(self) -> bool:
        return self.app_env == "production"

    @property
    def sync_database_url(self) -> str:
        """Sync DSN for Alembic / one-off scripts."""
        return str(self.database_url).replace("+asyncpg", "+psycopg")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
