"""What the shadow workforce records, and what its record adds up to."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Verdict = Literal["pending", "agreed", "edited", "rejected", "expired"]


class ShadowRun(BaseModel):
    """One thing an agent would have done, and what the person did instead."""

    id: str
    tenant_id: str
    process_id: str
    agent: str
    trigger_kind: str = ""
    dedupe_key: str = ""
    review_item_id: str | None = None

    predicted: dict[str, Any] = Field(default_factory=dict)
    predicted_at: datetime
    confidence: float = 0.0

    verdict: Verdict = "pending"
    observed: dict[str, Any] | None = None
    observed_at: datetime | None = None
    note: str = ""


class Scorecard(BaseModel):
    """One agent's record on one process.

    Accuracy counts only settled predictions. A pending one is not evidence in either
    direction, and counting it as either would let an agent look good by predicting things
    nobody ever decides.
    """

    process_id: str
    process_name: str = ""
    agent: str
    predictions: int = 0
    settled: int = 0
    agreed: int = 0
    edited: int = 0
    rejected: int = 0
    accuracy: float = 0.0
    # Edited counts as half: the agent had the right idea and the wrong words, which is worth
    # something but is not the same as being right.
    weighted: float = 0.0
    ready: bool = False
    needs: int = 0
    verdict_text: str = ""


class Scoreboard(BaseModel):
    window_days: int
    cards: list[Scorecard] = Field(default_factory=list)
    summary: str = ""
