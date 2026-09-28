"""Organisation record and onboarding stage (redesign B1).

The company name lives here and nowhere else. No module hardcodes one.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel

from core.db.pool import tenant_conn

Stage = Literal["no_connections", "learning", "ready"]
CONFIG_PATH = Path("config/processes.yaml")


@lru_cache(maxsize=1)
def _config(path: str = str(CONFIG_PATH)) -> dict[str, Any]:
    return dict(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def ready_min_cases() -> int:
    return int(_config()["onboarding"]["ready_min_cases"])


class Org(BaseModel):
    id: str
    name: str
    display_name: str
    locale: str
    is_demo: bool
    paused: bool
    created_at: datetime


class OrgStatus(BaseModel):
    stage: Stage
    connected_count: int
    process_count: int
    review_count: int
    ready_min_cases: int


async def get_org(tenant_id: str) -> Org | None:
    async with tenant_conn(tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT id, name, coalesce(display_name, name) AS display_name, locale,"
            " is_demo, paused, created_at FROM tenants WHERE id=$1",
            tenant_id,
        )
    return Org(**dict(row)) if row else None


async def ensure_org(
    tenant_id: str, name: str, *, locale: str = "en", is_demo: bool = False
) -> Org:
    async with tenant_conn(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO tenants (id, name, display_name, locale, is_demo)"
            " VALUES ($1,$2,$2,$3,$4)"
            " ON CONFLICT (id) DO UPDATE SET display_name = EXCLUDED.display_name,"
            " locale = EXCLUDED.locale, is_demo = EXCLUDED.is_demo",
            tenant_id,
            name,
            locale,
            is_demo,
        )
    org = await get_org(tenant_id)
    if org is None:  # pragma: no cover - the insert above guarantees a row
        msg = f"could not create org {tenant_id}"
        raise RuntimeError(msg)
    return org


async def org_status(tenant_id: str) -> OrgStatus:
    """Which of the three onboarding states the company is in.

    no_connections: nothing is plugged in yet.
    learning:       tools are connected but no process has enough cases to be worth showing.
    ready:          at least one process has cleared the threshold.
    """
    minimum = ready_min_cases()
    async with tenant_conn(tenant_id) as conn:
        connected = await conn.fetchval(
            "SELECT count(*) FROM connections WHERE tenant_id=$1 AND status='connected'",
            tenant_id,
        )
        processes = await conn.fetchval(
            "SELECT count(*) FROM processes WHERE tenant_id=$1", tenant_id
        )
        ready = await conn.fetchval(
            "SELECT count(*) FROM processes WHERE tenant_id=$1 AND case_count >= $2",
            tenant_id,
            minimum,
        )
        reviews = await conn.fetchval(
            "SELECT count(*) FROM review_items WHERE tenant_id=$1 AND status='open'",
            tenant_id,
        )

    connected_count = int(connected or 0)
    stage: Stage = "no_connections"
    if connected_count > 0:
        stage = "ready" if int(ready or 0) > 0 else "learning"

    return OrgStatus(
        stage=stage,
        connected_count=connected_count,
        process_count=int(processes or 0),
        review_count=int(reviews or 0),
        ready_min_cases=minimum,
    )
