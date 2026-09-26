"""Async Postgres pool with tenant scoping.

Every query runs inside a connection whose `plexus.tenant_id` GUC is set, which is what the
row-level security policies key on (spec 11).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg

from core.settings import Settings, get_settings

_pool: asyncpg.Pool | None = None


def dsn(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    return (
        f"postgresql://{s.postgres_user}:{s.postgres_password}"
        f"@{s.postgres_host}:{s.postgres_port}/{s.postgres_db}"
    )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn(), min_size=1, max_size=10, command_timeout=30)
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
