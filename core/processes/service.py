"""What a person sees about a way of working (redesign B3).

Everything the screen shows is assembled here: the plain name, how long it takes, where it
gets stuck, and how much Plexus is allowed to do. Raw numbers are kept alongside the words so
the technical panel can show them without the main view ever mentioning them.
"""

from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import BaseModel, Field

from core.db.pool import tenant_conn
from core.language import phrases
from core.language.format import Duration, duration
from core.language.service import describe_process, shape_from_metrics
from core.ledger import ledger
from core.ledger.models import Tier
from core.ledger.trust import compute_trust, load_config, next_transition

Health = Literal["smooth", "watch", "slow"]
CONFIG_PATH = Path("config/processes.yaml")

# The five rungs, as a person reads them. Level is 1-based; Tier is 0-based.
LEVEL_KEYS = ["watches", "explains", "suggests", "actsWithOk", "actsAlone"]

# Gap between label generations, so a per-minute vendor quota is not tripped by one batch.
PACE_SECONDS = 4.0


@lru_cache(maxsize=1)
def _config(path: str = str(CONFIG_PATH)) -> dict[str, Any]:
    return dict(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


class Slowest(BaseModel):
    from_step: str = ""
    to_step: str = ""
    text: str = ""
    duration: Duration | None = None


class Step(BaseModel):
    label: str
    order: int
    verb: str


class Wait(BaseModel):
    from_step: str
    to_step: str
    duration: Duration
    is_slowest: bool


class Autonomy(BaseModel):
    level: int = Field(ge=1, le=5)
    level_key: str
    decisions: int
    needed: int
    can_promote: bool
    reason: str
    paused: bool


class Technical(BaseModel):
    cases: int
    variants: int
    median_gaps: list[dict[str, Any]]
    bottleneck_transition: str
    trust_score: float
    trust_components: dict[str, float]
    tier: str


class ProcessSummary(BaseModel):
    id: str
    name: str
    description: str
    total_duration: Duration
    health: Health
    slowest: Slowest
    level: int
    paused: bool
    case_count: int
    tools: list[str]
    tools_text: str


class ProcessDetail(ProcessSummary):
    steps: list[Step]
    waits: list[Wait]
    help_tip: str
    autonomy: Autonomy
    technical: Technical


def classify_health(gaps_s: list[float]) -> Health:
    """Is one step holding this up, or is the work just long?

    Those are different questions and only the first is worth flagging. A process where every
    wait is similar is running as well as it can, however many days it takes end to end. So
    health compares the worst wait against the others rather than against the total: a
    three-step process has two waits, and an evenly paced one already puts half the time in
    each, which share-of-total would wrongly call a bottleneck.

    A fortnight of dead time is bad news whatever the rest looks like, hence the ceiling.
    """
    cfg = _config()["health"]
    if not gaps_s:
        return "smooth"
    worst = max(gaps_s)
    if worst >= float(cfg["slow_absolute_days"]) * 86400:
        return "slow"
    others = [g for g in gaps_s if g is not worst]
    if not others:
        return "smooth"
    baseline = sum(others) / len(others)
    if baseline <= 0:
        return "slow" if worst > 0 else "smooth"
    ratio = worst / baseline
    if ratio >= float(cfg["slow_ratio"]):
        return "slow"
    if ratio >= float(cfg["watch_ratio"]):
        return "watch"
    return "smooth"


def _j(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


async def _tools_for(tenant_id: str, process_id: str) -> list[str]:
    """Which connected tools this way of working actually shows up in."""
    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT source->>'source_id' AS source_id FROM event_log"
            " WHERE tenant_id=$1 AND objects @> $2::jsonb",
            tenant_id,
            json.dumps([{"object_type": process_id}]),
        )
    return sorted(r["source_id"] for r in rows if r["source_id"])


async def _rows(tenant_id: str, process_id: str | None = None) -> list[dict[str, Any]]:
    sql = (
        "SELECT p.*, s.tier, s.paused FROM processes p"
        " LEFT JOIN process_state s ON s.tenant_id=p.tenant_id AND s.process_id=p.id"
        " WHERE p.tenant_id=$1"
    )
    args: list[Any] = [tenant_id]
    if process_id:
        args.append(process_id)
        sql += f" AND p.id=${len(args)}"
    async with tenant_conn(tenant_id) as conn:
        return [dict(r) for r in await conn.fetch(sql, *args)]


async def _assemble(tenant_id: str, row: dict[str, Any], *, detail: bool, allow_model: bool) -> Any:
    process_id = row["id"]
    steps_raw = _j(row["steps"]) or []
    edges_raw = _j(row["edges"]) or []
    metrics = _j(row["metrics"]) or {}
    case_count = int(row["case_count"] or 0)
    tier = Tier.parse(row["tier"] or "OBSERVE")
    paused = bool(row["paused"])

    tools = await _tools_for(tenant_id, process_id)
    shape = shape_from_metrics(process_id, steps_raw, edges_raw, metrics, case_count, tools)
    language = await describe_process(tenant_id, shape, allow_model=allow_model)

    total_s = float(metrics.get("median_cycle_time_s", 0) or 0)
    gap_s = float(metrics.get("bottleneck_gap_s", 0) or 0)
    b_from = str(metrics.get("bottleneck_from", ""))
    b_to = str(metrics.get("bottleneck_to", ""))

    label_of = dict(zip([s["verb"] for s in steps_raw], language.steps, strict=False))

    slowest = Slowest(
        from_step=label_of.get(b_from, phrases.step_label(b_from)) if b_from else "",
        to_step=label_of.get(b_to, phrases.step_label(b_to)) if b_to else "",
        text=language.slowest_text,
        duration=duration(gap_s) if gap_s else None,
    )

    summary = ProcessSummary(
        id=process_id,
        name=language.name,
        description=language.description,
        total_duration=duration(total_s),
        health=classify_health([float(e["median_gap_s"]) for e in edges_raw]),
        slowest=slowest,
        level=int(tier) + 1,
        paused=paused,
        case_count=case_count,
        tools=tools,
        tools_text=phrases.tool_list(tools),
    )
    if not detail:
        return summary

    entries = await ledger.entries(tenant_id, process_id, limit=load_config().window_n)
    breakdown = compute_trust(list(reversed(entries)), load_config())
    transition = next_transition(tier, breakdown, load_config())
    cfg = load_config()
    next_tier = Tier(min(int(Tier.AUTONOMOUS), int(tier) + 1))

    return ProcessDetail(
        **summary.model_dump(),
        steps=[
            Step(
                label=language.steps[i] if i < len(language.steps) else s["verb"],
                order=i + 1,
                verb=s["verb"],
            )
            for i, s in enumerate(steps_raw)
        ],
        waits=[
            Wait(
                from_step=label_of.get(e["source"], phrases.step_label(e["source"])),
                to_step=label_of.get(e["target"], phrases.step_label(e["target"])),
                duration=duration(float(e["median_gap_s"])),
                is_slowest=e["source"] == b_from and e["target"] == b_to,
            )
            for e in edges_raw
        ],
        help_tip=language.help_tip,
        autonomy=Autonomy(
            level=int(tier) + 1,
            level_key=LEVEL_KEYS[int(tier)],
            decisions=breakdown.samples,
            needed=cfg.min_sample(next_tier) if tier < Tier.AUTONOMOUS else 0,
            can_promote=transition.eligible and not paused,
            reason=transition.reason,
            paused=paused,
        ),
        technical=Technical(
            cases=case_count,
            variants=int(metrics.get("variant_count", 0) or 0),
            median_gaps=[
                {
                    "from": e["source"],
                    "to": e["target"],
                    "seconds": e["median_gap_s"],
                    "count": e["count"],
                    "dependency": e["dependency"],
                }
                for e in edges_raw
            ],
            bottleneck_transition=f"{b_from} -> {b_to}" if b_from else "",
            trust_score=round(breakdown.trust, 3),
            trust_components={k: round(v, 4) for k, v in breakdown.terms.items()},
            tier=tier.name,
        ),
    )


async def list_processes(
    tenant_id: str, *, only_slow: bool = False, allow_model: bool = False
) -> list[ProcessSummary]:
    """The list as a person sees it, worst first.

    `allow_model` is off here on purpose: a request must never wait on a vendor. Wording comes
    from the cache when a background refresh has filled it, and from the rules when it has not.
    """
    out: list[ProcessSummary] = []
    for row in await _rows(tenant_id):
        summary = await _assemble(tenant_id, row, detail=False, allow_model=allow_model)
        if only_slow and summary.health == "smooth":
            continue
        out.append(summary)
    # Worst first: that is what someone opening this screen wants to see.
    order = {"slow": 0, "watch": 1, "smooth": 2}
    out.sort(key=lambda p: (order[p.health], -p.total_duration.seconds))
    return out


async def get_process(
    tenant_id: str, process_id: str, *, allow_model: bool = False
) -> ProcessDetail | None:
    rows = await _rows(tenant_id, process_id)
    if not rows:
        return None
    result = await _assemble(tenant_id, rows[0], detail=True, allow_model=allow_model)
    return cast(ProcessDetail, result)


async def refresh_labels(tenant_id: str) -> dict[str, str]:
    """Generate the wording for every process. Background work, never in a request.

    Called after mining and from `make labels`. Falls back to rules per process, so one
    vendor failure does not stop the rest.
    """
    results: dict[str, str] = {}
    rows = await _rows(tenant_id)
    for index, row in enumerate(rows):
        if index:
            # Free vendor tiers meter per minute, so the batch is paced rather than burst.
            await asyncio.sleep(PACE_SECONDS)
        process_id = row["id"]
        steps_raw = _j(row["steps"]) or []
        edges_raw = _j(row["edges"]) or []
        metrics = _j(row["metrics"]) or {}
        tools = await _tools_for(tenant_id, process_id)
        shape = shape_from_metrics(
            process_id, steps_raw, edges_raw, metrics, int(row["case_count"] or 0), tools
        )
        language = await describe_process(tenant_id, shape, allow_model=True)
        results[process_id] = f"{language.source}: {language.name}"
    return results
