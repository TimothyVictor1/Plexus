"""Seed a Plexus organisation.

    uv run python -m scripts.seed                 # the demo org, flagged is_demo
    uv run python -m scripts.seed --org acme --name "Acme AB"   # a real, empty org

The demo org is deterministic and industry-neutral: the same seed always produces the same
events. A real org starts empty and fills up as its tools are connected.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid

from agents.discover.miner import build_cases, mine
from agents.extract.ingest import Ingestor, seed_gazetteer
from core.db.migrate import migrate
from core.db.pool import close_pool, tenant_conn
from core.events.model import read_events
from core.graph.store import get_store
from core.org.service import ensure_org
from core.pii.boundary import get_boundary
from core.pii.vault import TokenVault
from scripts.fixtures.demo import (
    CUSTOMERS,
    DEMO_CONNECTIONS,
    DEMO_ORG_NAME,
    DEMO_TENANT,
    PEOPLE,
    PROCESS_SPECS,
    build,
)

# Industry-neutral policies. Scoped, so a rule only judges actions it can actually judge.
POLICIES = [
    (
        "POL-003",
        "Spending above 10 000 SEK needs someone to approve it",
        {"source_id": "accounting"},
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
        "Anything high risk always needs a person",
        {},
        "risk_class",
        "eq",
        "high",
        "require_approver",
    ),
]


async def seed_demo() -> None:
    org = await ensure_org(DEMO_TENANT, DEMO_ORG_NAME, locale="en", is_demo=True)
    print(f"org {org.id} ({org.display_name}) is_demo={org.is_demo}")

    fx = build()
    await seed_gazetteer(DEMO_TENANT, PEOPLE, CUSTOMERS)

    async with tenant_conn(DEMO_TENANT) as conn:
        for pid, name, scope, field, op, value, effect in POLICIES:
            await conn.execute(
                "INSERT INTO policies (id, tenant_id, name, scope, field, operator, value, effect)"
                " VALUES ($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT (tenant_id, id) DO UPDATE"
                " SET name=EXCLUDED.name, scope=EXCLUDED.scope, value=EXCLUDED.value,"
                " effect=EXCLUDED.effect",
                pid,
                DEMO_TENANT,
                name,
                json.dumps(scope),
                field,
                op,
                json.dumps(value),
                effect,
            )

        connection_ids: dict[str, str] = {}
        for category, provider, source_id in DEMO_CONNECTIONS:
            row = await conn.fetchrow(
                "INSERT INTO connections (id, tenant_id, category, provider, status, source_id,"
                " last_sync) VALUES ($1,$2,$3,$4,'connected',$5, now())"
                " ON CONFLICT (tenant_id, category, provider) DO UPDATE"
                " SET status='connected', last_sync=now() RETURNING id",
                str(uuid.uuid4()),
                DEMO_TENANT,
                category,
                provider,
                source_id,
            )
            connection_ids[source_id] = str(row["id"])

    store = get_store()
    await store.init_schema()
    ingestor = Ingestor(get_boundary(), TokenVault(), store)

    totals = {"documents": 0, "nodes": 0, "edges": 0, "events": 0}
    for source_id, items in sorted(fx.items.items()):
        counts = await ingestor.ingest(
            DEMO_TENANT, source_id, items, connection_id=connection_ids.get(source_id)
        )
        print(f"  {source_id:12} {counts}")
        for k, v in counts.items():
            totals[k] += v

    events = await read_events(DEMO_TENANT, limit=20000)
    cases = build_cases(events)

    # Each case's events share one object whose type is the process key, so grouping needs no
    # guesswork: read the key straight off the events.
    grouped: dict[str, list] = {}
    known = {spec.key for spec in PROCESS_SPECS}
    for case in cases:
        keys = {o.object_type for e in case.events for o in e.objects} & known
        if len(keys) == 1:
            grouped.setdefault(keys.pop(), []).append(case)

    async with tenant_conn(DEMO_TENANT) as conn:
        for key, group in sorted(grouped.items()):
            discovered = mine(group, key, key.replace("_", " ").capitalize())
            await conn.execute(
                "INSERT INTO processes (id, tenant_id, name, description, steps, edges,"
                " metrics, case_count) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)"
                " ON CONFLICT (tenant_id, id) DO UPDATE SET steps=EXCLUDED.steps,"
                " edges=EXCLUDED.edges, metrics=EXCLUDED.metrics,"
                " case_count=EXCLUDED.case_count, name=EXCLUDED.name",
                key,
                DEMO_TENANT,
                discovered.name,
                "",
                json.dumps([s.__dict__ for s in discovered.steps]),
                json.dumps([e.__dict__ for e in discovered.edges]),
                json.dumps(discovered.metrics),
                discovered.case_count,
            )
            await conn.execute(
                "INSERT INTO process_state (tenant_id, process_id, tier)"
                " VALUES ($1,$2,'OBSERVE') ON CONFLICT (tenant_id, process_id) DO NOTHING",
                DEMO_TENANT,
                key,
            )
            cycle = float(discovered.metrics["median_cycle_time_s"]) / 86400
            print(
                f"  {key:20} {len(discovered.steps)} steps  "
                f"{discovered.case_count:3} cases  {cycle:5.1f} d"
            )

    vault = await TokenVault().count(DEMO_TENANT)
    graph = await store.counts(DEMO_TENANT)
    await store.close()
    print(f"\ntotals {totals}\nvault {vault}\ngraph {graph}")


async def seed_empty(tenant_id: str, name: str) -> None:
    org = await ensure_org(tenant_id, name, is_demo=False)
    print(f"org {org.id} ({org.display_name}) created, no data")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a Plexus organisation")
    parser.add_argument("--org", default=DEMO_TENANT, help="tenant id")
    parser.add_argument("--name", default=None, help="display name")
    args = parser.parse_args()

    for applied in await migrate():
        print(f"migration {applied}")

    if args.org == DEMO_TENANT:
        await seed_demo()
    else:
        await seed_empty(args.org, args.name or args.org)
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
