"""Action pipeline types (spec 05)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.models.types import ModelId
from twin.engine import PredictedChange, SimulationReport

RiskClass = Literal["low", "medium", "high"]
Decision = Literal["approve", "reject", "escalate"]


class GraphRef(BaseModel):
    key: str
    kind: str
    why: str = ""


class ProposedAction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    process_id: str
    trigger_event_id: str | None = None
    target_source_id: str
    operation: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    rationale: str
    cited_context: list[GraphRef] = Field(default_factory=list)
    expected_effects: list[PredictedChange] = Field(default_factory=list)
    risk_class: RiskClass = "low"
    actor_model: ModelId
    trace_id: str = ""
    created_at: datetime | None = None
    status: str = "pending"
    simulation: SimulationReport | None = None


class VerdictReason(BaseModel):
    kind: Literal["policy", "graph_fact", "simulation", "uncertainty"]
    ref: str
    text: str


class Verdict(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action_id: str
    decision: Decision
    reasons: list[VerdictReason] = Field(default_factory=list)
    verifier_model: ModelId
    trace_id: str = ""


class HumanApproval(BaseModel):
    subject: str
    role: str
    at: datetime | None = None


class ExecutionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action_id: str
    verdict_id: str | None = None
    executed: bool
    outcome: Literal["executed", "held", "refused"]
    entry_type: str
    title: str
    detail: str
    write_result: dict[str, Any] = Field(default_factory=dict)
    reversal: dict[str, Any] | None = None
