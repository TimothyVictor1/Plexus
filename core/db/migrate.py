"""Apply SQL migrations in order, once each."""

from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from core.db.pool import dsn

MIGRATIONS = Path(__file__).parent / "migrations"


async def migrate() -> list[str]:
    conn = await asyncpg.connect(dsn())
    applied: list[str] = []
    try:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {r["name"] for r in await conn.fetch("SELECT name FROM schema_migrations")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in done:
                continue
            await conn.execute(path.read_text(encoding="utf-8"))
            await conn.execute("INSERT INTO schema_migrations (name) VALUES ($1)", path.name)
            applied.append(path.name)
    finally:
        await conn.close()
    return applied


if __name__ == "__main__":
    for name in asyncio.run(migrate()):
        print(f"applied {name}")
