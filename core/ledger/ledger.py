"""Append-only, hash-chained Autonomy Ledger (spec 04)."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from core.db.pool import tenant_conn
from core.ledger.models import ChainStatus, LedgerEntry, NewLedgerEntry

GENESIS = "0" * 64


def canonical(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def entry_hash(
    prev_hash: str,
    tenant_id: str,
    process_id: str,
    entry_type: str,
    actor: Mapping[str, object],
    payload: Mapping[str, object],
    ts: datetime,
    entry_id: str,
) -> str:
    material = "|".join(
        [
            prev_hash,
            tenant_id,
            process_id,
            entry_type,
            canonical(actor),
            canonical(payload),
            ts.isoformat(),
            entry_id,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _row_to_entry(row: Mapping[str, Any]) -> LedgerEntry:
    d = dict(row)
    for key in ("actor", "payload"):
        if isinstance(d[key], str):
            d[key] = json.loads(d[key])
    d["id"] = str(d["id"])
    return LedgerEntry(**d)


async def append(new: NewLedgerEntry) -> LedgerEntry:
    entry_id = str(uuid.uuid4())
    ts = datetime.now(tz=UTC)
    actor = new.actor.model_dump()
    async with tenant_conn(new.tenant_id) as conn:
        # Serialise appends per process so the chain stays linear.
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1))", f"{new.tenant_id}:{new.process_id}"
        )
        prev = await conn.fetchval(
            "SELECT hash FROM ledger_entries WHERE tenant_id=$1 AND process_id=$2"
            " ORDER BY seq DESC LIMIT 1",
            new.tenant_id,
            new.process_id,
        )
        prev_hash = prev or GENESIS
        digest = entry_hash(
            prev_hash,
            new.tenant_id,
            new.process_id,
            new.entry_type,
            actor,
            new.payload,
            ts,
            entry_id,
        )
        row = await conn.fetchrow(
            "INSERT INTO ledger_entries"
            " (id, tenant_id, process_id, entry_type, actor, payload, trace_id, ts,"
            " prev_hash, hash)"
            " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *",
            entry_id,
            new.tenant_id,
            new.process_id,
            new.entry_type,
            json.dumps(actor),
            json.dumps(new.payload, default=str),
            new.trace_id,
            ts,
            prev_hash,
            digest,
        )
    return _row_to_entry(row)


async def entries(
    tenant_id: str, process_id: str | None = None, entry_type: str | None = None, limit: int = 200
) -> list[LedgerEntry]:
    sql = "SELECT * FROM ledger_entries WHERE tenant_id=$1"
    args: list[object] = [tenant_id]
    if process_id:
        args.append(process_id)
        sql += f" AND process_id=${len(args)}"
    if entry_type:
        args.append(entry_type)
        sql += f" AND entry_type=${len(args)}"
    args.append(limit)
    sql += f" ORDER BY seq DESC LIMIT ${len(args)}"
    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch(sql, *args)
    return [_row_to_entry(r) for r in rows]


async def verify_chain(tenant_id: str, process_id: str) -> ChainStatus:
    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT * FROM ledger_entries WHERE tenant_id=$1 AND process_id=$2 ORDER BY seq",
            tenant_id,
            process_id,
        )
    prev_hash = GENESIS
    for row in rows:
        e = _row_to_entry(row)
        if e.prev_hash != prev_hash:
            return ChainStatus(
                process_id=process_id,
                ok=False,
                entries=len(rows),
                broken_at=e.seq,
                detail="prev_hash does not match the previous entry",
            )
        expected = entry_hash(
            e.prev_hash, e.tenant_id, e.process_id, e.entry_type, e.actor, e.payload, e.ts, e.id
        )
        if expected != e.hash:
            return ChainStatus(
                process_id=process_id,
                ok=False,
                entries=len(rows),
                broken_at=e.seq,
                detail="row content does not match its stored hash",
            )
        prev_hash = e.hash
    return ChainStatus(process_id=process_id, ok=True, entries=len(rows))


async def verify_all(tenant_id: str) -> list[ChainStatus]:
    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT process_id FROM ledger_entries WHERE tenant_id=$1", tenant_id
        )
    return [await verify_chain(tenant_id, r["process_id"]) for r in rows]
