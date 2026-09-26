"""Ledger types and tiers (spec 04)."""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

EntryType = Literal[
    "shadow_run",
    "suggestion",
    "approval",
    "rejection",
    "execution",
    "reversal",
    "promotion",
    "demotion",
    "manual_override",
    "refusal",
    "pause",
    "unpause",
]


class Tier(IntEnum):
    OBSERVE = 0
    EXPLAIN = 1
    SUGGEST = 2
    ACT_WITH_APPROVAL = 3
    AUTONOMOUS = 4

    @classmethod
    def parse(cls, name: str) -> Tier:
        return cls[name.upper()]

    @property
    def label(self) -> str:
        return self.name


class Actor(BaseModel):
    kind: Literal["human", "system", "model"]
    id: str
    role: str | None = None


class NewLedgerEntry(BaseModel):
    tenant_id: str
    process_id: str
    entry_type: EntryType
    actor: Actor
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str = ""


class LedgerEntry(BaseModel):
    seq: int
    id: str
    tenant_id: str
    process_id: str
    entry_type: EntryType
    actor: dict[str, Any]
    payload: dict[str, Any]
    trace_id: str
    ts: datetime
    prev_hash: str
    hash: str


class ChainStatus(BaseModel):
    process_id: str
    ok: bool
    entries: int
    broken_at: int | None = None
    detail: str | None = None


class TrustBreakdown(BaseModel):
    trust: float
    approval_rate: float
    reversal_rate: float
    recency: float
    blast_radius: float
    samples: int
    executions: int
    reversals: int
    days_since_error: float | None
    terms: dict[str, float]


class Transition(BaseModel):
    direction: Literal["promote", "demote", "hold"]
    from_tier: str
    to_tier: str
    reason: str
    eligible: bool = False
    blockers: list[str] = Field(default_factory=list)
