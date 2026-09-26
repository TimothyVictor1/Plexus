"""Process-wide settings loaded from the environment (see .env.example)."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(StrEnum):
    development = "development"
    test = "test"
    production = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    plexus_env: Env = Env.development
    plexus_log_level: str = "INFO"
    plexus_model_profile: str = "default"

    # Vendor credentials. Empty means that vendor is unavailable and the router says so
    # rather than silently routing somewhere else.
    google_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Where model inference physically happens, surfaced in the privacy section so the
    # product never claims a residency the configured provider does not actually give.
    model_data_region: str = "global"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "plexus"
    postgres_user: str = "plexus"
    postgres_password: str = "plexus"  # noqa: S105 - local dev default, overridden by env

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "plexuspassword"  # noqa: S105 - local dev default, overridden by env

    redis_url: str = "redis://localhost:6379/0"

    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"

    presidio_analyzer_url: str = "http://localhost:5002"
    presidio_anonymizer_url: str = "http://localhost:5001"

    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "plexus-api"

    oidc_issuer: str = "http://localhost:8080/realms/plexus"
    oidc_client_id: str = "plexus-dashboard"

    @property
    def is_production(self) -> bool:
        return self.plexus_env is Env.production


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
