"""Adapter contract (spec 01).

Every source system is reached through an adapter implementing `PlexusAdapter`. The types here
are the wire format between adapters and the core. Items are tokenised by the PII Boundary
before they leave the adapter process; `write` is callable only from core/action/executor.py.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

ItemKind = Literal["email", "message", "task", "file", "record"]
ChangeKind = Literal["created", "updated", "deleted"]


class AdapterCapabilities(BaseModel):
    read: bool = True
    write: bool = False  # generated adapters ship with this False (spec 08)
    watch: bool = False
    backfill: bool = True


class SourceRef(BaseModel):
    source_id: str
    external_id: str
    version: str | None = None
    url: str | None = None


class ActorRef(BaseModel):
    token: str = Field(description="Tokenised person or system id, e.g. <PERSON_7f3a>")
    kind: Literal["person", "system"]
    display_hint: str | None = Field(default=None, description="Tokenised; never clear text")


class SourceItem(BaseModel):
    tenant_id: str
    source_id: str
    external_id: str
    kind: ItemKind
    title: str
    body: str
    structured: dict[str, Any] = Field(default_factory=dict)
    actors: list[ActorRef] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None
    raw_ref: SourceRef


class SourceEvent(BaseModel):
    tenant_id: str
    source_id: str
    ref: SourceRef
    change: ChangeKind
    ts: datetime


class WriteOp(BaseModel):
    """Only constructed by core/action/executor.py."""

    tenant_id: str
    source_id: str
    operation: str
    arguments: dict[str, Any]
    idempotency_key: str


class WriteResult(BaseModel):
    ok: bool
    ref: SourceRef | None = None
    reversal: WriteOp | None = None
    message: str | None = None


class FieldSpec(BaseModel):
    name: str
    type: str
    is_id: bool = False
    pii_hint: str | None = None


class SourceSchema(BaseModel):
    fields: list[FieldSpec]
    record_types: list[str]


@runtime_checkable
class PlexusAdapter(Protocol):
    id: str
    capabilities: AdapterCapabilities

    def backfill(self, since: datetime | None) -> AsyncIterator[SourceItem]: ...

    def watch(self) -> AsyncIterator[SourceEvent]: ...

    async def read(self, ref: SourceRef) -> SourceItem: ...

    async def write(self, op: WriteOp) -> WriteResult: ...  # ONLY callable from executor

    def describe_schema(self) -> SourceSchema: ...
