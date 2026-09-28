"""Changing how much Plexus does, and the rules that stop it (redesign B4)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest

from core.db.pool import tenant_conn
from core.ledger import ledger
from core.ledger.models import Actor, NewLedgerEntry, Tier
from core.processes import autonomy, get_process

pytestmark = pytest.mark.integration

TENANT = "demo"


@pytest.fixture
async def process() -> AsyncIterator[str]:
    """A throwaway process of this test's own.

    The ledger is append-only by design, so approvals one test writes can never be cleared.
    Sharing a process between tests would leak a track record from one into the next, and the
    order they happened to run in would decide whether they passed.
    """
    process_id = f"test-autonomy-{uuid.uuid4().hex[:8]}"
    async with tenant_conn(TENANT) as conn:
        await conn.execute(
            "INSERT INTO processes (id, tenant_id, name, description, steps, edges, metrics,"
            " case_count) VALUES ($1,$2,'Test process','',"
            " '[]'::jsonb,'[]'::jsonb,'{}'::jsonb,0)",
            process_id,
            TENANT,
        )
        await conn.execute(
            "INSERT INTO process_state (tenant_id, process_id, tier) VALUES ($1,$2,'OBSERVE')",
            TENANT,
            process_id,
        )
    yield process_id
    async with tenant_conn(TENANT) as conn:
        await conn.execute(
            "DELETE FROM process_state WHERE tenant_id=$1 AND process_id=$2",
            TENANT,
            process_id,
        )
        await conn.execute("DELETE FROM processes WHERE tenant_id=$1 AND id=$2", TENANT, process_id)


async def _set(process_id: str, tier: Tier = Tier.OBSERVE, paused: bool = False) -> None:
    async with tenant_conn(TENANT) as conn:
        await conn.execute(
            "UPDATE process_state SET tier=$3, paused=$4 WHERE tenant_id=$1 AND process_id=$2",
            TENANT,
            process_id,
            tier.name,
            paused,
        )


async def _earn(process_id: str, n: int) -> None:
    """Give the process a real record of approvals so it can qualify."""
    for _ in range(n):
        await ledger.append(
            NewLedgerEntry(
                tenant_id=TENANT,
                process_id=process_id,
                entry_type="approval",
                actor=Actor(kind="human", id="tester", role="approver"),
                payload={},
            )
        )


async def test_promotion_is_refused_with_a_reason_a_person_can_act_on(process: str) -> None:
    outcome = await autonomy.promote(TENANT, process, "tester", "admin")
    assert outcome.ok is False
    assert outcome.reason
    assert "decisions" in outcome.reason


async def test_promotion_succeeds_once_the_record_justifies_it(process: str) -> None:
    await _earn(process, 30)
    outcome = await autonomy.promote(TENANT, process, "tester", "admin")
    assert outcome.ok is True
    assert outcome.to_level == outcome.from_level + 1
    detail = await get_process(TENANT, process)
    assert detail is not None
    assert detail.autonomy.level == outcome.to_level


async def test_a_paused_process_cannot_be_promoted(process: str) -> None:
    await _set(process, paused=True)
    await _earn(process, 30)
    outcome = await autonomy.promote(TENANT, process, "tester", "admin")
    assert outcome.ok is False
    assert "paused" in outcome.reason.lower()


async def test_pulling_back_never_has_to_be_earned(process: str) -> None:
    await _set(process, Tier.SUGGEST)
    outcome = await autonomy.demote(TENANT, process, "tester", "admin")
    assert outcome.ok is True
    assert outcome.to_level == 2


async def test_the_bottom_and_top_rungs_hold(process: str) -> None:
    assert (await autonomy.demote(TENANT, process, "t", "admin")).ok is False
    await _set(process, Tier.AUTONOMOUS)
    assert (await autonomy.promote(TENANT, process, "t", "admin")).ok is False


async def test_pause_and_resume_round_trip(process: str) -> None:
    assert (await autonomy.set_paused(TENANT, process, True, "t", "approver")).ok is True
    detail = await get_process(TENANT, process)
    assert detail is not None and detail.paused is True

    assert (await autonomy.set_paused(TENANT, process, True, "t", "approver")).ok is False
    assert (await autonomy.set_paused(TENANT, process, False, "t", "approver")).ok is True
    detail = await get_process(TENANT, process)
    assert detail is not None and detail.paused is False


async def test_every_change_is_written_to_the_ledger(process: str) -> None:
    await _set(process, Tier.SUGGEST)
    before = len(await ledger.entries(TENANT, process, entry_type="demotion", limit=200))
    await autonomy.demote(TENANT, process, "auditor", "admin")
    after = await ledger.entries(TENANT, process, entry_type="demotion", limit=200)
    assert len(after) == before + 1
    entry = after[0]
    assert entry.actor["id"] == "auditor"
    assert entry.payload["from"] and entry.payload["to"]
    assert entry.ts is not None


async def test_an_unknown_process_is_not_silently_created() -> None:
    with pytest.raises(autonomy.ProcessNotFoundError):
        await autonomy.promote(TENANT, "no-such-process", "t", "admin")
