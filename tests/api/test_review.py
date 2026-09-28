"""The review queue, end to end (redesign B5, B10)."""

from __future__ import annotations

import pytest

from core.db.pool import tenant_conn
from core.ledger import ledger
from core.ledger.models import Tier
from core.review import (
    ReviewItem,
    approve,
    count_open,
    create_from_triggers,
    done_today,
    open_items,
    skip,
)

pytestmark = pytest.mark.integration

TENANT = "demo"
SUGGESTING = ("quote_to_payment", "purchasing", "monthly_reporting")


async def _fresh_queue() -> list[ReviewItem]:
    """Clear the queue and rebuild it from whatever is genuinely stuck right now."""
    async with tenant_conn(TENANT) as conn:
        await conn.execute("DELETE FROM review_items WHERE tenant_id=$1", TENANT)
        await conn.execute("DELETE FROM triggers_seen WHERE tenant_id=$1", TENANT)
        for pid in SUGGESTING:
            await conn.execute(
                "INSERT INTO process_state (tenant_id, process_id, tier) VALUES ($1,$2,$3)"
                " ON CONFLICT (tenant_id, process_id) DO UPDATE SET tier=EXCLUDED.tier",
                TENANT,
                pid,
                Tier.SUGGEST.name,
            )
    await create_from_triggers(TENANT)
    return await open_items(TENANT)


async def test_stuck_work_becomes_something_a_person_can_decide() -> None:
    items = await _fresh_queue()
    assert items, "the demo has stuck work, so the queue should not be empty"
    for item in items:
        assert item.title and item.why and item.draft_text
        assert item.approve_label
        assert item.status == "open"


async def test_the_reason_states_a_fact_from_the_data() -> None:
    """The headline is never the model's to invent: it counts real days."""
    items = await _fresh_queue()
    assert any(any(ch.isdigit() for ch in item.why) for item in items)


async def test_nothing_is_created_twice_for_the_same_occurrence() -> None:
    await _fresh_queue()
    first = await count_open(TENANT)
    await create_from_triggers(TENANT)
    assert await count_open(TENANT) == first


async def test_a_process_that_only_watches_prepares_nothing() -> None:
    async with tenant_conn(TENANT) as conn:
        await conn.execute("DELETE FROM review_items WHERE tenant_id=$1", TENANT)
        await conn.execute("DELETE FROM triggers_seen WHERE tenant_id=$1", TENANT)
        for pid in SUGGESTING:
            await conn.execute(
                "UPDATE process_state SET tier='OBSERVE' WHERE tenant_id=$1 AND process_id=$2",
                TENANT,
                pid,
            )
    assert await create_from_triggers(TENANT) == []
    assert await count_open(TENANT) == 0


async def test_approving_executes_and_lands_in_the_ledger() -> None:
    """The whole loop: something waiting, a person says yes, it happens, it is recorded."""
    items = await _fresh_queue()
    before_count = len(items)
    item = items[0]

    before_entries = len(await ledger.entries(TENANT, item.process_id, limit=200))
    decision = await approve(TENANT, item.id, "e2e-approver")

    assert decision.ok is True
    assert decision.executed is True
    assert await count_open(TENANT) == before_count - 1

    after = await ledger.entries(TENANT, item.process_id, limit=200)
    assert len(after) > before_entries
    assert {e.entry_type for e in after[:3]} & {"execution", "approval"}
    assert any(e.actor["id"] == "e2e-approver" for e in after[:3])

    finished = await done_today(TENANT)
    assert any(d.id == item.id and d.status == "executed" for d in finished)


async def test_skipping_counts_against_the_process() -> None:
    items = await _fresh_queue()
    item = items[0]
    before = len(await ledger.entries(TENANT, item.process_id, entry_type="rejection", limit=200))

    decision = await skip(TENANT, item.id, "e2e-skipper")
    assert decision.ok is True
    assert decision.status == "skipped"

    after = await ledger.entries(TENANT, item.process_id, entry_type="rejection", limit=200)
    assert len(after) == before + 1


async def test_an_item_cannot_be_decided_twice() -> None:
    items = await _fresh_queue()
    item = items[0]
    assert (await skip(TENANT, item.id, "first")).ok is True
    second = await skip(TENANT, item.id, "second")
    assert second.ok is False
    assert "already" in second.title.lower()


async def test_an_unknown_item_is_reported_not_invented() -> None:
    with pytest.raises(LookupError):
        await approve(TENANT, "00000000-0000-0000-0000-000000000000", "nobody")
