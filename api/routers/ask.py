"""Asking questions about your own company (redesign B6)."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.deps import tenant_context
from core.ask import Answer, answer, suggestions
from core.ask.service import stream
from core.tenancy import TenantContext

router = APIRouter(tags=["ask"])

# Answering costs a model call, so one organisation cannot be allowed to spend without bound.
# In-process is honest for a single API container; a shared counter is the next step when
# there is more than one.
RATE_LIMIT = 20
RATE_WINDOW_S = 60.0
_recent: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit(tenant_id: str) -> None:
    now = time.monotonic()
    calls = _recent[tenant_id]
    while calls and now - calls[0] > RATE_WINDOW_S:
        calls.popleft()
    if len(calls) >= RATE_LIMIT:
        raise HTTPException(
            429, "That is a lot of questions at once. Give it a minute and try again."
        )
    calls.append(now)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = None


@router.post("/ask", response_model=Answer)
async def ask(body: AskRequest, ctx: TenantContext = Depends(tenant_context)) -> Answer:
    _rate_limit(ctx.tenant_id)
    return await answer(ctx.tenant_id, body.question, ctx.subject, body.conversation_id)


@router.post("/ask/stream")
async def ask_stream(
    body: AskRequest, ctx: TenantContext = Depends(tenant_context)
) -> StreamingResponse:
    """The same answer, delivered as it is ready."""
    _rate_limit(ctx.tenant_id)
    return StreamingResponse(
        stream(ctx.tenant_id, body.question, ctx.subject, body.conversation_id),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )


@router.get("/ask/suggestions", response_model=list[str])
async def ask_suggestions(ctx: TenantContext = Depends(tenant_context)) -> list[str]:
    return await suggestions(ctx.tenant_id)
