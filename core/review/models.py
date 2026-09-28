"""Review item shapes (redesign B5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ReviewStatus = Literal["open", "approved", "edited", "skipped", "executed", "failed"]


class ReviewItem(BaseModel):
    id: str
    process_id: str
    process_name: str = ""
    action_id: str | None = None
    kind: str
    title: str
    why: str
    draft_text: str
    draft_fields: dict[str, Any] = Field(default_factory=dict)
    approve_label: str
    status: ReviewStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    decided_by: str | None = None
    decided_at: datetime | None = None


class Decision(BaseModel):
    ok: bool
    status: ReviewStatus
    title: str
    detail: str
    executed: bool = False
