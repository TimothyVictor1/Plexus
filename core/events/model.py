"""Unified object-centric event model (spec 02)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from adapters._contract.base import ActorRef, SourceRef
from core.db.pool import tenant_conn
from core.events.verbs import is_known


class ObjectRef(BaseModel):
    object_type: str
    object_id: str
    source: SourceRef | None = None

    @property
    def qualified(self) -> str:
        return f"{self.object_type}:{self.object_id}"


class PlexusEvent(BaseModel):
    tenant_id: str
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ts: datetime
    actor: ActorRef
    verb: str
    objects: list[ObjectRef]
    source: SourceRef
    attributes: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    synthesised: bool = False
    trace_id: str = ""

    @field_validator("verb")
    @classmethod
    def _known_verb(cls, v: str) -> str:
        if not is_known(v):
            msg = f"verb {v!r} is not in the vocabulary; propose it via OntologyProposal"
            raise ValueError(msg)
        return v


async def write_events(tenant_id: str, events: list[PlexusEvent]) -> int:
    if not events:
        return 0
    async with tenant_conn(tenant_id) as conn:
        await conn.executemany(
            "INSERT INTO event_log"
            " (event_id, tenant_id, ts, actor, verb, objects, source, attributes,"
            "  confidence, synthesised, trace_id)"
            " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)"
            " ON CONFLICT (event_id) DO NOTHING",
            [
                (
                    e.event_id,
                    e.tenant_id,
                    e.ts,
                    json.dumps(e.actor.model_dump()),
                    e.verb,
                    json.dumps([o.model_dump() for o in e.objects]),
                    json.dumps(e.source.model_dump()),
                    json.dumps(e.attributes, default=str),
                    e.confidence,
                    e.synthesised,
                    e.trace_id,
                )
                for e in events
            ],
        )
    return len(events)


async def read_events(tenant_id: str, limit: int = 5000) -> list[PlexusEvent]:
    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT * FROM event_log WHERE tenant_id=$1 ORDER BY ts LIMIT $2", tenant_id, limit
        )
    out: list[PlexusEvent] = []
    for row in rows:
        d = dict(row)
        for key in ("actor", "objects", "source", "attributes"):
            if isinstance(d[key], str):
                d[key] = json.loads(d[key])
        d["event_id"] = str(d["event_id"])
        out.append(PlexusEvent(**d))
    return out
