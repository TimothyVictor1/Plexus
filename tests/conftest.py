from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

import core.graph.store as graph_store
from core.db.pool import close_pool

REPO_ROOT = Path(__file__).resolve().parent.parent


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("PLEXUS_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="integration tests need PLEXUS_INTEGRATION=1 and `make up`")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(autouse=True)
async def _reset_clients() -> AsyncIterator[None]:
    """Give every test its own database and graph connections.

    pytest-asyncio runs each test in a fresh event loop, while the asyncpg pool and the Neo4j
    driver are module-level singletons bound to the loop that created them. Without this, the
    second test to touch the database inherits a pool whose loop has already closed.
    """
    yield
    await close_pool()
    if graph_store._store is not None:
        await graph_store._store.close()
        graph_store._store = None
