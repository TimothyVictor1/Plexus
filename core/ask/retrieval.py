"""Finding the parts of a company's own records that bear on a question (redesign B6).

Full-text search over the tokenised documents, plus the process figures, which is where most
"how long" and "who does what" questions are actually answered. Everything returned carries
the source it came from, so the answer can cite it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.db.pool import tenant_conn
from core.language import phrases

STOPWORDS = frozenset(
    """a an and are as at be by do does for from how i in is it long of on or our take takes
    that the to us we what when where which who why with you your""".split()
)


@dataclass
class Passage:
    text: str
    source_id: str
    external_id: str
    title: str
    kind: str
    rank: float


@dataclass
class ProcessFact:
    process_id: str
    name: str
    text: str


def _terms(question: str) -> list[str]:
    words = re.findall(r"[A-Za-zÅÄÖåäö0-9]{3,}", question.lower())
    return [w for w in words if w not in STOPWORDS][:8]


async def search_documents(tenant_id: str, question: str, limit: int = 6) -> list[Passage]:
    terms = _terms(question)
    if not terms:
        return []
    query = " | ".join(terms)
    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT source_id, external_id, title, kind, body_tokenised,"
            " ts_rank(search_tsv, to_tsquery('simple', $2)) AS rank"
            " FROM documents"
            " WHERE tenant_id = $1 AND search_tsv @@ to_tsquery('simple', $2) AND NOT erased"
            " ORDER BY rank DESC, created_at DESC LIMIT $3",
            tenant_id,
            query,
            limit,
        )
    return [
        Passage(
            text=(r["body_tokenised"] or "")[:400],
            source_id=r["source_id"],
            external_id=r["external_id"],
            title=r["title"] or r["external_id"],
            kind=r["kind"],
            rank=float(r["rank"]),
        )
        for r in rows
    ]


async def process_facts(tenant_id: str, question: str) -> list[ProcessFact]:
    """The measured figures. Most questions about time are answered from these, not from text."""
    from core.processes import list_processes

    terms = set(_terms(question))
    relevant: set[str] = set()
    facts: list[ProcessFact] = []
    for process in await list_processes(tenant_id):
        words = set(_terms(f"{process.name} {process.description} {process.slowest.text}"))
        overlap = len(terms & words)
        slowest = (
            f" The longest wait is {process.slowest.text}, at {process.slowest.duration.text}."
            if process.slowest.duration and process.slowest.text
            else ""
        )
        text = (
            f"{process.name}: {process.description}. It happened {process.case_count} times "
            f"and takes {process.total_duration.text} end to end.{slowest} "
            f"Seen in {process.tools_text}. Plexus {phrases.step_label('')}"
        ).replace(" Plexus ", " ")
        facts.append(ProcessFact(process_id=process.id, name=process.name, text=text.strip()))
        if overlap:
            facts[-1] = ProcessFact(process.id, process.name, text.strip())
    # Anything the question actually mentions first, then the rest as background.
    facts.sort(key=lambda f: (f.process_id not in relevant, f.name))
    return facts[:6]


def as_sources(passages: list[Passage]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for p in passages:
        key = f"{p.source_id}:{p.external_id}"
        if key not in seen:
            seen[key] = {
                "tool": phrases.tool_label(p.source_id),
                "title": phrases.humanise_tokens(p.title),
                "reference": key,
                "kind": p.kind,
            }
    return list(seen.values())
