"""Async Postgres pool with tenant scoping.

Every query runs inside a connection whose `plexus.tenant_id` GUC is set, which is what the
row-level security policies key on (spec 11).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import asyncpg

from core.settings import Settings, get_settings

_pool: asyncpg.Pool | None = None

# Query parameters a managed Postgres puts in its URL for libpq's benefit. asyncpg either
# understands them as its own arguments or rejects them outright, so they are lifted out of
# the URL here rather than handed through.
_LIFTED = {
    "sslmode",
    "channel_binding",
    "pgbouncer",
    "connect_timeout",
    "options",
    "target_session_attrs",
}


def _split_url(url: str) -> tuple[str, dict[str, str]]:
    """Return the URL asyncpg should see, and the parameters lifted out of it."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    lifted = {k: v for k, v in query.items() if k in _LIFTED}
    kept = {k: v for k, v in query.items() if k not in _LIFTED}
    clean = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))
    return clean, lifted


def dsn(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    if s.database_url:
        return _split_url(s.database_url)[0]
    return (
        f"postgresql://{s.postgres_user}:{s.postgres_password}"
        f"@{s.postgres_host}:{s.postgres_port}/{s.postgres_db}"
    )


def connect_kwargs(settings: Settings | None = None) -> dict[str, Any]:
    """Connection arguments implied by the URL a managed Postgres gave us.

    Two things matter beyond the address. TLS, because a hosted database refuses a plaintext
    connection and the mode arrives as a URL parameter asyncpg does not read. And prepared
    statements, because a transaction-pooling proxy such as pgbouncer hands each statement to
    whichever backend is free, so a statement prepared on one is not there on the next; the
    cache has to be off or every other query fails.
    """
    s = settings or get_settings()
    if not s.database_url:
        return {}
    _, lifted = _split_url(s.database_url)
    kwargs: dict[str, Any] = {}
    mode = lifted.get("sslmode", "")
    if mode and mode != "disable":
        # asyncpg's own spelling. "require" encrypts without demanding a local CA bundle,
        # which is what a hosted database expects of a client.
        kwargs["ssl"] = "require" if mode in {"require", "prefer", "allow"} else mode
    if lifted.get("pgbouncer") == "true" or "-pooler." in s.database_url:
        kwargs["statement_cache_size"] = 0
    return kwargs


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = await asyncpg.create_pool(
            dsn(s),
            min_size=1,
            max_size=max(1, s.postgres_pool_max),
            command_timeout=30,
            **connect_kwargs(s),
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def tenant_conn(tenant_id: str) -> AsyncIterator[asyncpg.Connection]:
    """A connection with the tenant GUC set, so RLS applies for the whole block."""
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT set_config('plexus.tenant_id', $1, true)", tenant_id)
        yield conn


async def fetch(tenant_id: str, sql: str, *args: Any) -> list[asyncpg.Record]:
    async with tenant_conn(tenant_id) as conn:
        return list(await conn.fetch(sql, *args))


async def fetchrow(tenant_id: str, sql: str, *args: Any) -> asyncpg.Record | None:
    async with tenant_conn(tenant_id) as conn:
        return await conn.fetchrow(sql, *args)


async def execute(tenant_id: str, sql: str, *args: Any) -> str:
    async with tenant_conn(tenant_id) as conn:
        return str(await conn.execute(sql, *args))
