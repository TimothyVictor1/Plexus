"""Export a snapshot of a running Plexus so the console can be shown without a service.

    uv run python -m scripts.export_snapshot

The console is a thin client: every screen reads from the Plexus service. That is the right
architecture and the wrong one for a link someone opens to see what the product is, because a
console with no service to talk to shows nothing at all.

This writes the real output of a real running system to static files the console can serve in
preview mode. Nothing here is invented: it is the same JSON the service returns, captured once.
Preview mode is clearly labelled in the console and is read-only, because the writes it would
otherwise make belong to a service that is not there.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.ask import suggestions
from core.db.pool import close_pool
from core.insights import top_insights
from core.org import get_org, org_status
from core.processes import get_process, list_processes
from core.review import done_today, open_items
from scripts.fixtures.demo import DEMO_TENANT
from twin.organisation import build_model, demand_changes, person_leaves

OUT = Path("dashboard/public/preview")


def _encode(value: Any) -> Any:
    """Everything the service returns, as JSON: models, dates and the odd set."""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, set | frozenset):
        return sorted(value)
    raise TypeError(type(value))


def write(name: str, payload: Any) -> None:
    path = OUT / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, default=_encode, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"  {path}  {path.stat().st_size // 1024} kB")


def dump(model: Any) -> Any:
    return json.loads(json.dumps(model, default=_encode, ensure_ascii=False))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Capture a console preview snapshot")
    parser.add_argument("--org", default=DEMO_TENANT)
    args = parser.parse_args()
    tenant = args.org

    print(f"capturing {tenant}")
    org = await get_org(tenant)
    status = await org_status(tenant)
    processes = await list_processes(tenant)
    reviews = await open_items(tenant)

    write(
        "org",
        {
            "id": org.id if org else tenant,
            "name": org.name if org else tenant,
            "display_name": org.display_name if org else tenant,
            "locale": org.locale if org else "en",
            "is_demo": True,
            "paused": False,
            "created_at": org.created_at if org else datetime.now(),
        },
    )
    write("org-status", dump(status))
    write("processes", {"processes": dump(processes)})

    for process in processes:
        detail = await get_process(tenant, process.id)
        if detail is not None:
            write(f"process-{process.id}", dump(detail))

    write(
        "home",
        {
            "org_name": org.display_name if org else tenant,
            "is_demo": True,
            "status": dump(status),
            "open_reviews": dump(reviews[:3]),
            "open_review_count": len(reviews),
            "insights": dump(await top_insights(tenant)),
            "tools": [
                {"category": c, "connected": True}
                for c in ("accounting", "calendar", "crm", "email", "files", "hr")
            ],
        },
    )
    write("review", {"open": dump(reviews), "done_today": dump(await done_today(tenant))})
    write("ask-suggestions", await suggestions(tenant))

    model = await build_model(tenant)
    write("twin", dump(model))

    # A couple of worked answers, so the what-if screen shows something real without a service
    # to compute a fresh one.
    scenarios: dict[str, Any] = {}
    for person in model.people[:6]:
        scenarios[f"person_leaves:{person.token}"] = dump(person_leaves(model, person.token))
    for process in model.processes:
        for multiplier in (0.5, 2.0, 3.0):
            scenarios[f"demand_changes:{process.id}:{multiplier}"] = dump(
                demand_changes(model, process.id, multiplier)
            )
    write("twin-scenarios", scenarios)

    from adapters.connectors import list_connections
    from adapters.connectors.registry import catalogue, privacy_facts

    connections = await list_connections(tenant)
    write(
        "connections",
        {
            "connections": dump(connections),
            "connected_count": sum(1 for c in connections if c.status == "connected"),
            "total": len(connections),
            "privacy": privacy_facts(),
        },
    )
    write("connections-catalogue", dump(catalogue()))

    await close_pool()
    print("\nsnapshot written. The console serves it when no service address is configured.")


if __name__ == "__main__":
    asyncio.run(main())
