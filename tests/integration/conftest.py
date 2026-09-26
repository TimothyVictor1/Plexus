"""Integration fixtures.

pytest-asyncio gives each test its own event loop, while the asyncpg pool and the Neo4j driver
are module-level singletons bound to the loop that created them. Resetting both between tests
keeps every test honest about opening its own connections.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

import core.graph.store as graph_store
from core.db.pool import close_pool


@pytest.fixture(autouse=True)
async def _reset_clients() -> AsyncIterator[None]:
    yield
    await close_pool()
    if graph_store._store is not None:
        await graph_store._store.close()
        graph_store._store = None
