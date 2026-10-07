"""Answering a question from the company's own records (redesign B6).

Two rules make this trustworthy. Everything the model sees has already been through the PII
Boundary, so no real name or number reaches a vendor. And when retrieval finds nothing, the
answer says so rather than filling the gap.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, Field

from core.ask.entities import as_notes, find_entities
from core.ask.retrieval import _terms, as_sources, process_facts, search_documents
from core.db.pool import tenant_conn
from core.models.router import get_router, render
from core.models.types import ModelUnavailableError, Role, SchemaValidationError


class Source(BaseModel):
    tool: str
    title: str
    reference: str
    kind: str = ""


class Answer(BaseModel):
    text: str
    sources: list[Source] = Field(default_factory=list)
    conversation_id: str | None = None
    grounded: bool = True


SYSTEM = """You answer questions about a small company, for someone who works there and is not
technical.

Rules:
- Use only the notes provided. If they do not answer the question, say plainly that you cannot
  tell from what is connected, and say what would answer it.
- Never invent a number, a name, a date or an amount.
- Names and numbers appear as placeholders like <PERSON_1a2b>. Refer to them as "a customer",
  "a colleague", "a supplier". Never repeat a placeholder back.
- Two or three sentences. Plain language, no jargon, no bullet points.
- Lead with the answer."""


class AnswerText(BaseModel):
    answer: str


def _notes(facts: list[Any], passages: list[Any], entity_notes: str = "") -> str:
    lines = ["What Plexus has measured about how this company works:"]
    lines += [f"  - {f.text}" for f in facts]
    if entity_notes:
        lines += ["", entity_notes]
    if passages:
        lines += ["", "Relevant records:"]
        lines += [f"  - [{p.source_id}] {p.title}: {p.text[:220]}" for p in passages]
    return "\n".join(lines)


def _cannot_tell(question: str) -> str:
    return (
        "I cannot tell from what is connected. Nothing in the tools Plexus can see mentions "
        f"{question.strip().rstrip('?')}. Connecting the tool where that work happens would "
        "let me answer it."
    )


async def answer(
    tenant_id: str, question: str, subject: str, conversation_id: str | None = None
) -> Answer:
    question = question.strip()
    if not question:
        return Answer(text="Ask me anything about how your company works.", grounded=False)

    passages = await search_documents(tenant_id, question)
    facts = await process_facts(tenant_id, question)
    # Where a named thing has got to is not written in any document: it is the shape of the
    # events that touched it. Document search alone cannot answer "what is happening with X".
    entities = await find_entities(tenant_id, _terms(question), question)
    entity_notes = as_notes(entities)

    if not passages and not facts and not entities:
        return Answer(text=_cannot_tell(question), sources=[], grounded=False)

    try:
        completion = await get_router().complete(
            Role.workhorse,
            render(
                [
                    ("system", SYSTEM),
                    ("user", f"{_notes(facts, passages, entity_notes)}\n\nQ: {question}"),
                ]
            ),
            tenant_id=tenant_id,
            schema=AnswerText,
            max_tokens=1500,
        )
        text = str(completion.data.get("answer") or "").strip()
    except (ModelUnavailableError, SchemaValidationError):
        text = ""

    if not text:
        # No model, but the measured facts are still true and still useful.
        if facts:
            text = facts[0].text
        elif entities:
            text = entities[0].sentence()
        else:
            text = _cannot_tell(question)

    sources = [Source(**s) for s in as_sources(passages)]
    conversation_id = await _remember(tenant_id, subject, conversation_id, question, text, sources)
    return Answer(text=text, sources=sources, conversation_id=conversation_id, grounded=True)


async def stream(
    tenant_id: str, question: str, subject: str, conversation_id: str | None = None
) -> AsyncIterator[str]:
    """Server-sent events, so the answer appears as it is ready rather than all at once."""
    result = await answer(tenant_id, question, subject, conversation_id)
    words = result.text.split(" ")
    for index in range(0, len(words), 4):
        chunk = " ".join(words[index : index + 4])
        yield f"data: {json.dumps({'delta': chunk + ' '})}\n\n"
    payload = {
        "done": True,
        "sources": [s.model_dump() for s in result.sources],
        "conversation_id": result.conversation_id,
        "grounded": result.grounded,
    }
    yield f"data: {json.dumps(payload)}\n\n"


async def _remember(
    tenant_id: str,
    subject: str,
    conversation_id: str | None,
    question: str,
    text: str,
    sources: list[Source],
) -> str:
    async with tenant_conn(tenant_id) as conn:
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())
            await conn.execute(
                "INSERT INTO conversations (id, tenant_id, subject, title) VALUES ($1,$2,$3,$4)",
                conversation_id,
                tenant_id,
                subject,
                question[:120],
            )
        for role, body, srcs in (("user", question, []), ("assistant", text, sources)):
            await conn.execute(
                "INSERT INTO messages (id, tenant_id, conversation_id, role, text, sources)"
                " VALUES ($1,$2,$3,$4,$5,$6)",
                str(uuid.uuid4()),
                tenant_id,
                conversation_id,
                role,
                body,
                json.dumps([s.model_dump() for s in srcs]),
            )
    return conversation_id


async def suggestions(tenant_id: str) -> list[str]:
    """Three questions worth asking, drawn from what Plexus currently knows."""
    from core.insights import top_insights
    from core.processes import list_processes

    found = await top_insights(tenant_id)
    processes = await list_processes(tenant_id)
    out: list[str] = []

    slow = next((p for p in processes if p.health == "slow"), None)
    if slow and slow.slowest.text:
        out.append(f"Why does {slow.name.lower()} take so long?")
    if found:
        out.append("What changed in our work this month?")
    if processes:
        out.append(f"How does {processes[-1].name.lower()} normally work?")

    if not out:
        out = [
            "What can you see about how we work?",
            "Which tools are connected?",
            "What is waiting for me?",
        ]
    return out[:3]
