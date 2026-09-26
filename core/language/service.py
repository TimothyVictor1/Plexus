"""The plain-language layer (redesign B2).

Everything a person reads about a process comes from here, resolved in this order:

  1. an override someone typed, which always wins,
  2. a cached generated wording, valid while the process keeps the same shape,
  3. rule-based wording computed on the spot.

The model is given structure only: verbs, counts and durations. No document text, no names,
no addresses. There is nothing personal in the prompt to leak, which a test asserts.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field

from core.db.pool import tenant_conn
from core.language import phrases
from core.language.format import humanise
from core.models.router import get_router, render
from core.models.types import ModelUnavailableError, Role, SchemaValidationError

KIND = "process"
PROMPT_VERSION = 2

# Models like to restate the label they were asked for. The screen already says "Slowest:",
# so anything the model puts in front of the phrase has to come back off.
_LEAD_INS = (
    "slowest:",
    "slowest is",
    "the slowest is",
    "the slowest step is",
    "the longest wait is",
    "longest wait:",
    "it is",
    "this is",
)


class ProcessLanguage(BaseModel):
    """How one process is described everywhere in the product."""

    name: str = Field(description="Short name for this way of working, in plain English")
    description: str = Field(description="One line: where it starts and where it ends")
    steps: list[str] = Field(default_factory=list, description="A label per step, in order")
    slowest_text: str = Field(default="", description="The longest wait, as a phrase")
    help_tip: str = Field(default="", description="One concrete thing Plexus could do")
    source: str = "rules"


class ProcessShape(BaseModel):
    """The structure handed to the model. Deliberately free of any content."""

    process_id: str
    step_verbs: list[str]
    step_counts: list[int]
    transitions: list[dict[str, Any]]
    bottleneck_from: str
    bottleneck_to: str
    bottleneck_wait: str
    total_wait: str
    case_count: int
    tools: list[str]

    def signature(self) -> str:
        material = json.dumps(
            {
                "v": PROMPT_VERSION,
                "steps": self.step_verbs,
                "edges": sorted((t["from"], t["to"]) for t in self.transitions),
                "slow": [self.bottleneck_from, self.bottleneck_to],
            },
            sort_keys=True,
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def clean_phrase(text: str) -> str:
    """Turn a model's answer into something that reads correctly after 'Slowest: '."""
    cleaned = text.strip()
    changed = True
    while changed:
        changed = False
        lowered = cleaned.lower()
        for lead in _LEAD_INS:
            if lowered.startswith(lead):
                cleaned = cleaned[len(lead) :].lstrip(" :,")
                changed = True
                break
    cleaned = cleaned.rstrip(". ")
    return cleaned[:1].lower() + cleaned[1:] if cleaned else cleaned


def rule_based(shape: ProcessShape) -> ProcessLanguage:
    """The floor: always available, never wrong, just plainer than a model would write."""
    return ProcessLanguage(
        name=phrases.process_name(shape.step_verbs),
        description=phrases.process_description(shape.step_verbs),
        steps=[phrases.step_label(v) for v in shape.step_verbs],
        slowest_text=(
            phrases.transition_phrase(shape.bottleneck_from, shape.bottleneck_to)
            if shape.bottleneck_from
            else ""
        ),
        help_tip=(
            phrases.help_tip(shape.bottleneck_from, shape.bottleneck_to)
            if shape.bottleneck_from
            else ""
        ),
        source="rules",
    )


SYSTEM = """You write for an office manager at a small company. They are clever but not
technical, and they have never heard of process mining.

Rules:
- Plain English. Never use: process mining, event log, variant, dependency, bottleneck,
  transition, autonomy, tier, entity, adapter, pipeline.
- Name the work the way a colleague would say it out loud.
- Step labels are two or three words.
- The help tip names one concrete, useful thing, and never promises anything unsafe.
- Never invent detail that is not in the structure you were given."""


def _user_prompt(shape: ProcessShape) -> str:
    tools = ", ".join(shape.tools) or "unknown"
    lines = [
        "A repeated piece of work was observed in this company's own tools.",
        f"It happened {shape.case_count} times. Tools involved: {tools}.",
        "",
        "The steps, in order, recorded as event types:",
    ]
    lines += [
        f"  {i + 1}. {verb} (seen {count} times)"
        for i, (verb, count) in enumerate(zip(shape.step_verbs, shape.step_counts, strict=False))
    ]
    lines += ["", "Typical waits between steps:"]
    lines += [f"  {t['from']} -> {t['to']}: {t['wait']}" for t in shape.transitions]
    lines += [
        "",
        f"The longest wait is {shape.bottleneck_from} -> {shape.bottleneck_to}, "
        f"which takes {shape.bottleneck_wait}. The whole thing takes {shape.total_wait}.",
        "",
        "Give the name, the one-line description, and a label for each step in order.",
        "For slowest_text, give ONLY the phrase that completes 'Slowest: ...'. Start with a "
        "lower-case word, do not repeat the word 'slowest', and do not restate the duration.",
        "For help_tip, give one concrete thing Plexus could do about that wait.",
    ]
    return "\n".join(lines)


async def _generate(tenant_id: str, shape: ProcessShape) -> ProcessLanguage | None:
    """Ask the model. Returns None if it is unreachable or gives an unusable answer."""
    try:
        completion = await get_router().complete(
            Role.workhorse,
            render([("system", SYSTEM), ("user", _user_prompt(shape))]),
            tenant_id=tenant_id,
            schema=ProcessLanguage,
            max_tokens=2048,
        )
    except (ModelUnavailableError, SchemaValidationError):
        return None
    data = completion.data
    if not data.get("name"):
        return None
    language = ProcessLanguage(**{**data, "source": "model"})
    language.slowest_text = clean_phrase(language.slowest_text)
    # The screen puts its own punctuation after the description, so the model's must come off.
    language.description = language.description.strip().rstrip(".")
    language.name = language.name.strip().rstrip(".")
    # A model that returns the wrong number of step labels would silently mislabel the
    # timeline, so fall back to rules for the labels rather than guess at the alignment.
    if len(language.steps) != len(shape.step_verbs):
        language.steps = [phrases.step_label(v) for v in shape.step_verbs]
    return language


async def _read_override(tenant_id: str, target_id: str) -> str | None:
    async with tenant_conn(tenant_id) as conn:
        value = await conn.fetchval(
            "SELECT text FROM label_overrides WHERE tenant_id=$1 AND kind=$2 AND target_id=$3",
            tenant_id,
            KIND,
            target_id,
        )
    return str(value) if value is not None else None


async def _read_cache(tenant_id: str, target_id: str, signature: str) -> ProcessLanguage | None:
    async with tenant_conn(tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT payload, signature FROM label_cache"
            " WHERE tenant_id=$1 AND kind=$2 AND target_id=$3",
            tenant_id,
            KIND,
            target_id,
        )
    if row is None or row["signature"] != signature:
        return None
    payload = row["payload"]
    return ProcessLanguage(**(json.loads(payload) if isinstance(payload, str) else payload))


async def _write_cache(
    tenant_id: str, target_id: str, signature: str, language: ProcessLanguage, model: str
) -> None:
    async with tenant_conn(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO label_cache (tenant_id, kind, target_id, signature, payload, source,"
            " model) VALUES ($1,$2,$3,$4,$5,$6,$7)"
            " ON CONFLICT (tenant_id, kind, target_id) DO UPDATE SET signature=EXCLUDED.signature,"
            " payload=EXCLUDED.payload, source=EXCLUDED.source, model=EXCLUDED.model,"
            " created_at=now()",
            tenant_id,
            KIND,
            target_id,
            signature,
            json.dumps(language.model_dump()),
            language.source,
            model,
        )


async def describe_process(
    tenant_id: str, shape: ProcessShape, *, allow_model: bool = True
) -> ProcessLanguage:
    signature = shape.signature()

    cached = await _read_cache(tenant_id, shape.process_id, signature)
    language = cached or rule_based(shape)

    if cached is None and allow_model:
        generated = await _generate(tenant_id, shape)
        if generated is not None:
            language = generated
            await _write_cache(
                tenant_id,
                shape.process_id,
                signature,
                generated,
                get_router().model_id(Role.workhorse).model,
            )

    override = await _read_override(tenant_id, shape.process_id)
    if override:
        language = language.model_copy(update={"name": override, "source": "override"})
    return language


async def set_override(tenant_id: str, target_id: str, text: str, author: str) -> None:
    """A person renaming something. Their wording wins from then on."""
    async with tenant_conn(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO label_overrides (tenant_id, kind, target_id, text, author)"
            " VALUES ($1,$2,$3,$4,$5) ON CONFLICT (tenant_id, kind, target_id)"
            " DO UPDATE SET text=EXCLUDED.text, author=EXCLUDED.author, created_at=now()",
            tenant_id,
            KIND,
            target_id,
            text.strip(),
            author,
        )


def shape_from_metrics(
    process_id: str,
    steps: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    metrics: dict[str, Any],
    case_count: int,
    tools: list[str],
) -> ProcessShape:
    """Build the model's view of a process from what the miner stored."""
    return ProcessShape(
        process_id=process_id,
        step_verbs=[s["verb"] for s in steps],
        step_counts=[int(s.get("frequency", 0)) for s in steps],
        transitions=[
            {"from": e["source"], "to": e["target"], "wait": humanise(float(e["median_gap_s"]))}
            for e in edges
        ],
        bottleneck_from=str(metrics.get("bottleneck_from", "")),
        bottleneck_to=str(metrics.get("bottleneck_to", "")),
        bottleneck_wait=humanise(float(metrics.get("bottleneck_gap_s", 0) or 0)),
        total_wait=humanise(float(metrics.get("median_cycle_time_s", 0) or 0)),
        case_count=case_count,
        tools=tools,
    )
