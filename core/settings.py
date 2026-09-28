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

    # Comma-separated origins the console may be served from, beyond localhost.
    plexus_console_origins: str = ""

    # A managed Postgres hands out one URL rather than five variables, and it is the only way
    # some hosts expose the database at all. When set it wins; the parts below are the local
    # Compose defaults.
    database_url: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "plexus"
    postgres_user: str = "plexus"
    postgres_password: str = "plexus"  # noqa: S105 - local dev default, overridden by env

    # How many connections one process may hold. A long-lived server can afford a pool; a
    # serverless function is one of many short-lived copies sharing the same database, so it
    # takes fewer and leans on the host's connection pooler.
    postgres_pool_max: int = 10

    # The graph is a second store and not every host offers one. Left off, Plexus runs on
    # Postgres alone and the one screen that draws the graph says so instead of failing.
    graph_enabled: bool = True

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "plexuspassword"  # noqa: S105 - local dev default, overridden by env

    redis_url: str = "redis://localhost:6379/0"

    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"

    # "temporal" keeps a durable worker, which is the default and what the engineering rules
    # ask for. "cron" is for a host that cannot keep a worker alive: the same job functions are
    # called over HTTP on a schedule instead.
    jobs_scheduler: str = "temporal"
    # Shared secret the cron trigger presents. CRON_SECRET is what a serverless host sets by
    # convention; PLEXUS_CRON_SECRET is the same thing named our way. Either will do.
    cron_secret: str = ""
    plexus_cron_secret: str = ""

    @property
    def scheduler_secret(self) -> str:
        return self.cron_secret or self.plexus_cron_secret

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
