"""Overview, graph, processes and events."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query

from api.deps import tenant_context
from core.db.pool import tenant_conn
from core.graph.store import get_store
from core.ledger import ledger
from core.ledger.models import Tier
from core.ledger.trust import compute_trust, load_config, next_transition
from core.pii.vault import TokenVault
from core.tenancy import TenantContext

router = APIRouter(tags=["overview"])


def _j(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


@router.get("/overview")
async def overview(ctx: TenantContext = Depends(tenant_context)) -> dict[str, Any]:
    t = ctx.tenant_id
    async with tenant_conn(t) as conn:
        docs = await conn.fetchval("SELECT count(*) FROM documents WHERE tenant_id=$1", t)
        events = await conn.fetchval("SELECT count(*) FROM event_log WHERE tenant_id=$1", t)
        by_kind = await conn.fetch(
            "SELECT kind, count(*) AS c FROM documents WHERE tenant_id=$1 GROUP BY kind", t
        )
        procs = await conn.fetch(
            "SELECT p.id, p.name, p.case_count, p.metrics, s.tier, s.paused"
            " FROM processes p LEFT JOIN process_state s"
            " ON s.tenant_id = p.tenant_id AND s.process_id = p.id"
            " WHERE p.tenant_id=$1 ORDER BY p.name",
            t,
        )
        pending = await conn.fetchval(
            "SELECT count(*) FROM proposed_actions WHERE tenant_id=$1 AND status='pending'", t
        )
        calls = await conn.fetchrow(
            "SELECT count(*) AS n, coalesce(sum(cost_usd),0) AS cost,"
            " coalesce(avg(latency_ms),0) AS latency FROM model_calls WHERE tenant_id=$1",
            t,
        )
        paused = await conn.fetchval("SELECT paused FROM tenants WHERE id=$1", t)
        writes = await conn.fetchval("SELECT count(*) FROM adapter_records WHERE tenant_id=$1", t)

    chains = await ledger.verify_all(t)
    store = get_store()
    try:
        graph = await store.counts(t)
    except Exception:
        graph = {}

    return {
        "tenant": {"id": t, "paused": bool(paused)},
        "documents": docs,
        "documents_by_kind": {r["kind"]: r["c"] for r in by_kind},
        "events": events,
        "graph": graph,
        "graph_nodes": sum(graph.values()),
        "vault_entries": await TokenVault().count(t),
        "pending_actions": pending,
        "adapter_writes": writes,
        "model_calls": {
            "count": calls["n"],
            "cost_usd": float(calls["cost"]),
            "avg_latency_ms": round(float(calls["latency"]), 1),
        },
        "chains": [c.model_dump() for c in chains],
        "chain_ok": all(c.ok for c in chains) if chains else True,
        "processes": [
            {
                "id": p["id"],
                "name": p["name"],
                "tier": p["tier"] or "OBSERVE",
                "paused": bool(p["paused"]),
                "case_count": p["case_count"],
                "metrics": _j(p["metrics"]),
            }
            for p in procs
        ],
    }


@router.get("/graph/nodes")
async def graph_nodes(
    q: str = Query(default=""),
    limit: int = Query(default=60, le=200),
    ctx: TenantContext = Depends(tenant_context),
) -> dict[str, Any]:
    rows = await get_store().search(ctx.tenant_id, q, limit)
    return {"nodes": rows}


@router.get("/graph/nodes/{key:path}")
async def graph_node(
    key: str,
    depth: int = Query(default=1, ge=1, le=3),
    ctx: TenantContext = Depends(tenant_context),
) -> dict[str, Any]:
    return await get_store().neighbourhood(ctx.tenant_id, key, depth)


@router.get("/processes")
async def processes(ctx: TenantContext = Depends(tenant_context)) -> dict[str, Any]:
    t = ctx.tenant_id
    cfg = load_config()
    async with tenant_conn(t) as conn:
        rows = await conn.fetch(
            "SELECT p.*, s.tier, s.trust, s.paused FROM processes p"
            " LEFT JOIN process_state s ON s.tenant_id=p.tenant_id AND s.process_id=p.id"
            " WHERE p.tenant_id=$1 ORDER BY p.name",
            t,
        )
    out = []
    for r in rows:
        entries = await ledger.entries(t, r["id"], limit=cfg.window_n)
        breakdown = compute_trust(list(reversed(entries)), cfg)
        tier = Tier.parse(r["tier"] or "OBSERVE")
        transition = next_transition(tier, breakdown, cfg)
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "steps": _j(r["steps"]),
                "edges": _j(r["edges"]),
                "metrics": _j(r["metrics"]),
                "case_count": r["case_count"],
                "tier": tier.name,
                "paused": bool(r["paused"]),
                "trust": breakdown.model_dump(),
                "transition": transition.model_dump(),
                "thresholds": cfg.thresholds,
                "min_samples": cfg.min_samples,
            }
        )
    return {"processes": out}


@router.get("/events")
async def events(
    limit: int = Query(default=60, le=500), ctx: TenantContext = Depends(tenant_context)
) -> dict[str, Any]:
    async with tenant_conn(ctx.tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT event_id, ts, verb, actor, objects, source FROM event_log"
            " WHERE tenant_id=$1 ORDER BY ts DESC LIMIT $2",
            ctx.tenant_id,
            limit,
        )
    return {
        "events": [
            {
                "event_id": str(r["event_id"]),
                "ts": r["ts"],
                "verb": r["verb"],
                "actor": _j(r["actor"]),
                "objects": _j(r["objects"]),
                "source": _j(r["source"]),
            }
            for r in rows
        ]
    }


@router.get("/documents")
async def documents(
    q: str = Query(default=""),
    limit: int = Query(default=40, le=200),
    ctx: TenantContext = Depends(tenant_context),
) -> dict[str, Any]:
    async with tenant_conn(ctx.tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT source_id, external_id, kind, title, body_tokenised, created_at"
            " FROM documents WHERE tenant_id=$1"
            " AND ($2 = '' OR title ILIKE '%'||$2||'%' OR body_tokenised ILIKE '%'||$2||'%')"
            " ORDER BY created_at DESC LIMIT $3",
            ctx.tenant_id,
            q,
            limit,
        )
    return {"documents": [dict(r) for r in rows]}
