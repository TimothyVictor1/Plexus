"""Seed a full Plexus tenant: migrate, ingest fixtures, mine processes, open the inbox.

    uv run python -m scripts.seed

Everything it writes is derived from scripts/fixtures/nordvik.py. Run it as often as you like;
it is idempotent apart from the ledger, which is append-only by design.
"""

from __future__ import annotations

import asyncio
import json

from agents.discover.miner import build_cases, mine
from agents.extract.ingest import Ingestor, seed_gazetteer
from core.db.migrate import migrate
from core.db.pool import close_pool, tenant_conn
from core.events.model import read_events
from core.graph.store import get_store
from core.pii.boundary import get_boundary
from core.pii.vault import TokenVault
from scripts.fixtures.nordvik import CUSTOMERS, PEOPLE, TENANT, build

# A rule that cannot be evaluated fails closed, so each rule carries the scope it applies to.
# A spending limit has no business judging a task that involves no money.
POLICIES = [
    (
        "POL-003",
        "Spending above 10 000 SEK requires an approver",
        {"source_id": "economy"},
        "arguments.amount",
        "gt",
        10000,
        "require_approver",
    ),
    (
        "POL-007",
        "Personal data must stay in the EU",
        {},
        "target.region",
        "not_in",
        ["EU", "eu-north-1", "eu-west-1"],
        "block",
    ),
    (
        "POL-011",
        "High-risk operations always need a person",
        {},
        "risk_class",
        "eq",
        "high",
        "require_approver",
    ),
]

PROCESS_NAMES = {
    "quote_to_invoice": ("proc-quote", "Enquiry to quote to invoice"),
    "onboarding": ("proc-onboard", "New-hire onboarding"),
    "monthly_report": ("proc-report", "Monthly reporting"),
}


async def main() -> None:
    applied = await migrate()
    for name in applied:
        print(f"migration {name}")

    fx = build()

    async with tenant_conn(TENANT) as conn:
        await conn.execute(
            "INSERT INTO tenants (id, name) VALUES ($1,$2) ON CONFLICT (id) DO NOTHING",
            TENANT,
            "Nordvik Konsult AB",
        )
    await seed_gazetteer(TENANT, PEOPLE, CUSTOMERS)

    async with tenant_conn(TENANT) as conn:
        for pid, name, scope, field, op, value, effect in POLICIES:
            await conn.execute(
                "INSERT INTO policies (id, tenant_id, name, scope, field, operator, value, effect)"
                " VALUES ($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT (tenant_id, id) DO UPDATE"
                " SET name=EXCLUDED.name, scope=EXCLUDED.scope, value=EXCLUDED.value,"
                " effect=EXCLUDED.effect",
                pid,
                TENANT,
                name,
                json.dumps(scope),
                field,
                op,
                json.dumps(value),
                effect,
            )

    store = get_store()
    await store.init_schema()
    ingestor = Ingestor(get_boundary(), TokenVault(), store)

    totals = {"documents": 0, "nodes": 0, "edges": 0, "events": 0}
    for source_id, items in (("gmail", fx.emails), ("clickup", fx.tasks), ("gdrive", fx.files)):
        counts = await ingestor.ingest(TENANT, source_id, items)
        print(f"ingested {source_id}: {counts}")
        for k, v in counts.items():
            totals[k] += v

    events = await read_events(TENANT)
    cases = build_cases(events)
    print(f"cases: {len(cases)}")

    by_prefix: dict[str, list] = {"quote": [], "onboard": [], "report": [], "other": []}
    for case in cases:
        objs = {o.object_id for e in case.events for o in e.objects}
        bucket = next(
            (p for p in ("quote", "onboard", "report") if any(str(o).startswith(p) for o in objs)),
            "other",
        )
        by_prefix[bucket].append(case)

    async with tenant_conn(TENANT) as conn:
        for key, (pid, label) in PROCESS_NAMES.items():
            bucket = {
                "quote_to_invoice": "quote",
                "onboarding": "onboard",
                "monthly_report": "report",
            }[key]
            group = by_prefix[bucket]
            if not group:
                continue
            discovered = mine(group, pid, label)
            await conn.execute(
                "INSERT INTO processes (id, tenant_id, name, description, steps, edges,"
                " metrics, case_count) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)"
                " ON CONFLICT (tenant_id, id) DO UPDATE SET steps=EXCLUDED.steps,"
                " edges=EXCLUDED.edges, metrics=EXCLUDED.metrics, case_count=EXCLUDED.case_count",
                pid,
                TENANT,
                discovered.name,
                f"Mined from {discovered.case_count} cases in the event log.",
                json.dumps([s.__dict__ for s in discovered.steps]),
                json.dumps([e.__dict__ for e in discovered.edges]),
                json.dumps(discovered.metrics),
                discovered.case_count,
            )
            await conn.execute(
                "INSERT INTO process_state (tenant_id, process_id, tier)"
                " VALUES ($1,$2,'OBSERVE') ON CONFLICT (tenant_id, process_id) DO NOTHING",
                TENANT,
                pid,
            )
            print(
                f"mined {pid}: {len(discovered.steps)} steps, "
                f"{discovered.case_count} cases, "
                f"cycle {discovered.metrics['median_cycle_time_s'] / 86400:.1f} d"
            )

    vault_count = await TokenVault().count(TENANT)
    graph_counts = await store.counts(TENANT)
    await store.close()
    await close_pool()

    print(f"\ntotals: {totals}")
    print(f"vault entries: {vault_count}")
    print(f"graph: {graph_counts}")


if __name__ == "__main__":
    asyncio.run(main())
