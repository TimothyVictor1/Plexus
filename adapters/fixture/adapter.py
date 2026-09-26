"""A writable fixture adapter (spec 01 contract).

`write` is callable only from core/action/executor.py; the architecture test enforces that.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from adapters._contract.base import (
    AdapterCapabilities,
    SourceEvent,
    SourceItem,
    SourceRef,
    SourceSchema,
    WriteOp,
    WriteResult,
)
from core.db.pool import tenant_conn


class WriteDisabledError(RuntimeError):
    """The adapter's write capability is off; only an admin may enable it."""


class FixtureAdapter:
    """Stands in for ClickUp in the pilot. Records live in adapter_records."""

    def __init__(self, source_id: str = "clickup", *, write_enabled: bool = True) -> None:
        self.id = source_id
        self.capabilities = AdapterCapabilities(
            read=True, write=write_enabled, watch=False, backfill=True
        )

    async def backfill(self, since: datetime | None) -> AsyncIterator[SourceItem]:
        return
        yield  # pragma: no cover

    async def watch(self) -> AsyncIterator[SourceEvent]:
        return
        yield  # pragma: no cover

    async def read(self, ref: SourceRef) -> SourceItem:
        raise NotImplementedError

    async def records(self, tenant_id: str) -> list[dict[str, Any]]:
        async with tenant_conn(tenant_id) as conn:
            rows = await conn.fetch(
                "SELECT external_id, record_type, fields, updated_at FROM adapter_records"
                " WHERE tenant_id=$1 AND source_id=$2 ORDER BY updated_at DESC",
                tenant_id,
                self.id,
            )
        out = []
        for r in rows:
            fields = r["fields"]
            out.append(
                {
                    "external_id": r["external_id"],
                    "record_type": r["record_type"],
                    "fields": json.loads(fields) if isinstance(fields, str) else fields,
                    "updated_at": r["updated_at"],
                }
            )
        return out

    async def write(self, op: WriteOp) -> WriteResult:
        """Only the executor calls this, and only with restored (clear-text) arguments."""
        if not self.capabilities.write:
            raise WriteDisabledError(self.id)

        external_id = str(op.arguments.get("external_id") or op.idempotency_key[:12])
        record_type = op.operation.split(".")[-1]

        async with tenant_conn(op.tenant_id) as conn:
            before = await conn.fetchrow(
                "SELECT fields FROM adapter_records WHERE tenant_id=$1 AND source_id=$2"
                " AND external_id=$3",
                op.tenant_id,
                op.source_id,
                external_id,
            )
            await conn.execute(
                "INSERT INTO adapter_records (id, tenant_id, source_id, external_id,"
                " record_type, fields, updated_at)"
                " VALUES ($1,$2,$3,$4,$5,$6, now())"
                " ON CONFLICT (tenant_id, source_id, external_id)"
                " DO UPDATE SET fields = EXCLUDED.fields, updated_at = now(),"
                " record_type = EXCLUDED.record_type",
                str(uuid.uuid4()),
                op.tenant_id,
                op.source_id,
                external_id,
                record_type,
                json.dumps(op.arguments, default=str),
            )

        reversal: WriteOp | None = None
        if before is not None:
            prior = before["fields"]
            reversal = WriteOp(
                tenant_id=op.tenant_id,
                source_id=op.source_id,
                operation=op.operation,
                arguments=json.loads(prior) if isinstance(prior, str) else dict(prior),
                idempotency_key=f"revert-{op.idempotency_key}",
            )
        else:
            reversal = WriteOp(
                tenant_id=op.tenant_id,
                source_id=op.source_id,
                operation=f"{op.source_id}.delete",
                arguments={"external_id": external_id, "_delete": True},
                idempotency_key=f"revert-{op.idempotency_key}",
            )

        return WriteResult(
            ok=True,
            ref=SourceRef(source_id=op.source_id, external_id=external_id),
            reversal=reversal,
            message=f"{op.operation} applied to {external_id}",
        )

    def describe_schema(self) -> SourceSchema:
        return SourceSchema(fields=[], record_types=["task", "invoice", "file"])


_registry: dict[str, FixtureAdapter] = {}


def get_adapter(source_id: str) -> FixtureAdapter:
    if source_id not in _registry:
        _registry[source_id] = FixtureAdapter(source_id)
    return _registry[source_id]
