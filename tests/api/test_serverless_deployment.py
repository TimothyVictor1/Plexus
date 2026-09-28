"""Plexus on a host that gives it Postgres and nothing else.

Locally, Compose provides a graph store, a Temporal worker, Presidio and Redis. A serverless
host provides none of them. That must not change what the product does — every screen a person
uses is answered from Postgres and the event log — so these tests pin down the three places the
difference is visible, and that each one degrades into an honest answer rather than a failure.
"""

from __future__ import annotations

import base64
import secrets
from collections.abc import AsyncIterator
from typing import cast

import httpx
import pytest

from api.health import HttpCheck, TcpCheck, default_checks
from api.main import create_app
from core.db.pool import connect_kwargs, dsn
from core.graph.store import GraphUnavailableError, get_store, graph_enabled
from core.pii.kms import EnvKMS, FileKMS, RootKeyError, decode_root_key, default_kms
from core.settings import Settings


def hosted(**overrides: object) -> Settings:
    """Settings shaped like a serverless deployment: one managed Postgres, nothing else."""
    base: dict[str, object] = {
        "database_url": "postgresql://u:p@db.example.com:5432/plexus?sslmode=require",
        "graph_enabled": False,
        "jobs_scheduler": "cron",
        "redis_url": "",
        "presidio_analyzer_url": "",
        "presidio_anonymizer_url": "",
        "postgres_pool_max": 2,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# ----------------------------------------------------------------- the database URL
def test_database_url_wins_over_the_compose_defaults() -> None:
    assert dsn(hosted()) == "postgresql://u:p@db.example.com:5432/plexus"


def test_compose_parts_are_used_when_no_url_is_given() -> None:
    s = Settings(database_url="", postgres_host="localhost", postgres_db="plexus")
    assert dsn(s) == "postgresql://plexus:plexus@localhost:5432/plexus"


@pytest.mark.parametrize("scheme", ["postgres", "postgresql"])
def test_either_scheme_is_accepted(scheme: str) -> None:
    """Hosts hand out both spellings; asyncpg only understands one of them."""
    s = hosted(database_url=f"{scheme}://u:p@h/plexus")
    assert dsn(s).startswith("postgresql://")


def test_libpq_only_parameters_are_lifted_out_of_the_url() -> None:
    """asyncpg rejects these outright, so they must not reach it inside the URL."""
    s = hosted(database_url="postgresql://u:p@h/plexus?sslmode=require&channel_binding=require&x=1")
    assert "sslmode" not in dsn(s)
    assert "channel_binding" not in dsn(s)
    assert "x=1" in dsn(s), "parameters asyncpg does understand are left alone"


def test_tls_is_asked_for_when_the_url_requires_it() -> None:
    assert connect_kwargs(hosted())["ssl"] == "require"


def test_no_tls_is_forced_on_a_local_stack() -> None:
    assert connect_kwargs(Settings(database_url="")) == {}


def test_prepared_statements_are_off_behind_a_transaction_pooler() -> None:
    """A pooler hands each statement to whichever backend is free, so a cached plan is not there.

    Without this every other query fails against a pooled connection string.
    """
    pooled = hosted(database_url="postgresql://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/plexus")
    assert connect_kwargs(pooled)["statement_cache_size"] == 0
    assert "statement_cache_size" not in connect_kwargs(hosted())


# ----------------------------------------------------------------- the missing graph
def test_the_graph_is_off_when_the_deployment_has_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.graph.store.get_settings", hosted)
    assert graph_enabled() is False


def test_asking_for_a_store_that_is_not_there_refuses_clearly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("core.graph.store.get_settings", hosted)
    with pytest.raises(GraphUnavailableError):
        get_store()


def test_the_graph_is_on_for_the_local_stack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.graph.store.get_settings", Settings)
    assert graph_enabled() is True


# ----------------------------------------------------------------- health tells the truth
def _names(settings: Settings) -> set[str]:
    return {cast("TcpCheck | HttpCheck", c).name for c in default_checks(settings)}


def test_health_only_reports_what_this_deployment_actually_uses() -> None:
    """Otherwise a serverless deployment reports itself down forever, and looks broken."""
    assert _names(hosted()) == {"postgres"}


def test_health_reports_the_whole_stack_when_it_is_there() -> None:
    assert _names(Settings()) == {
        "postgres",
        "neo4j",
        "redis",
        "temporal",
        "presidio-analyzer",
        "presidio-anonymizer",
    }


def test_health_checks_the_database_the_service_is_actually_pointed_at() -> None:
    """With a URL configured, probing the Compose defaults would check the wrong machine."""
    pg = next(
        c for c in default_checks(hosted()) if isinstance(c, TcpCheck) and c.name == "postgres"
    )
    assert pg.host == "db.example.com"


def test_temporal_is_not_probed_when_the_schedule_is_a_cron() -> None:
    assert "temporal" not in _names(hosted(jobs_scheduler="cron"))
    assert "temporal" in _names(Settings(jobs_scheduler="temporal"))


# ----------------------------------------------------------------- the cron secret
def test_either_spelling_of_the_cron_secret_is_accepted() -> None:
    """CRON_SECRET is the hosting convention; PLEXUS_CRON_SECRET is ours."""
    assert Settings(cron_secret="a").scheduler_secret == "a"
    assert Settings(plexus_cron_secret="b").scheduler_secret == "b"
    assert Settings().scheduler_secret == ""


# ----------------------------------------------------------------- the cron endpoint
@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """The service as the host sees it, with no health probes to slow the test down."""
    app = create_app()
    app.state.health_checks = []
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_cron_is_closed_when_no_secret_is_configured(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unconfigured deployment must not be drivable by a stranger who knows the path."""
    monkeypatch.setattr("api.routers.jobs.get_settings", Settings)
    r = await client.post("/v1/jobs/maintenance")
    assert r.status_code == 503


async def test_cron_rejects_a_wrong_secret(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("api.routers.jobs.get_settings", lambda: Settings(cron_secret="right"))
    for headers in (
        {},
        {"Authorization": "Bearer wrong"},
        {"X-Plexus-Cron": "wrong"},
    ):
        r = await client.post("/v1/jobs/maintenance", headers=headers)
        assert r.status_code == 401, headers


async def test_cron_is_not_in_the_documented_api_twice(client: httpx.AsyncClient) -> None:
    """A hosted cron may only send GET, so both verbs work — but the schema describes one."""
    paths = (await client.get("/v1/openapi.json")).json()["paths"]
    assert list(paths["/v1/jobs/maintenance"]) == ["post"]


# ----------------------------------------------------------------- the root key
def test_a_key_from_the_environment_is_preferred_to_a_key_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A host that sets the variable is saying its disk is not somewhere to keep a key."""
    monkeypatch.setenv("PLEXUS_KMS_KEY", secrets.token_hex(32))
    assert isinstance(default_kms(), EnvKMS)


def test_the_key_file_is_used_when_the_environment_has_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PLEXUS_KMS_KEY", raising=False)
    assert isinstance(default_kms(), FileKMS)


def test_the_same_key_derives_the_same_tenant_key() -> None:
    """The seeding run and the serving process must agree, or the vault is unreadable."""
    raw = secrets.token_hex(32)
    assert EnvKMS(decode_root_key(raw)).data_key("demo") == EnvKMS(decode_root_key(raw)).data_key(
        "demo"
    )


def test_a_different_key_derives_a_different_tenant_key() -> None:
    a = EnvKMS(decode_root_key(secrets.token_hex(32))).data_key("demo")
    b = EnvKMS(decode_root_key(secrets.token_hex(32))).data_key("demo")
    assert a != b, "a per-cold-start key would silently corrupt every token"


def test_tenants_never_share_a_key() -> None:
    kms = EnvKMS(decode_root_key(secrets.token_hex(32)))
    assert kms.data_key("demo") != kms.data_key("other")


@pytest.mark.parametrize("spelling", ["hex", "base64", "text"])
def test_a_key_is_read_in_whichever_spelling_it_arrives(spelling: str) -> None:
    """It passes through a secret store and a copy-paste before it reaches us."""
    root = secrets.token_bytes(32)
    raw = {
        "hex": root.hex(),
        "base64": base64.b64encode(root).decode(),
        "text": "x" * 40,
    }[spelling]
    assert len(decode_root_key(raw)) >= 32
    EnvKMS(decode_root_key(raw))  # must not raise


def test_a_key_too_short_to_derive_from_is_refused() -> None:
    """Better a loud refusal at boot than personal details protected by four characters."""
    with pytest.raises(RootKeyError):
        EnvKMS(b"short")
