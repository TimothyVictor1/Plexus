"""The processes endpoints against the demo seed (redesign B3, B10)."""

from __future__ import annotations

import pytest

from core.processes import get_process, list_processes

pytestmark = pytest.mark.integration

TENANT = "demo"
JARGON = {
    "mined",
    "event log",
    "dependency",
    "variant",
    "rung",
    "trust score",
    "blast radius",
    "adapter",
    "bottleneck",
    "transition",
    "tier",
}


async def test_the_list_returns_every_discovered_way_of_working() -> None:
    found = await list_processes(TENANT)
    assert len(found) == 6
    assert all(p.case_count > 0 for p in found)
    assert all(p.tools for p in found)


async def test_the_worst_is_shown_first() -> None:
    found = await list_processes(TENANT)
    order = {"slow": 0, "watch": 1, "smooth": 2}
    assert [order[p.health] for p in found] == sorted(order[p.health] for p in found)


async def test_the_slow_filter_hides_healthy_work() -> None:
    slow = await list_processes(TENANT, only_slow=True)
    assert slow
    assert all(p.health != "smooth" for p in slow)
    assert len(slow) < len(await list_processes(TENANT))


async def test_quote_to_payment_is_slow_because_of_the_invoice_wait() -> None:
    detail = await get_process(TENANT, "quote_to_payment")
    assert detail is not None
    assert detail.health == "slow"
    assert detail.technical.bottleneck_transition == "delivered -> invoiced"
    slowest = [w for w in detail.waits if w.is_slowest]
    assert len(slowest) == 1
    assert slowest[0].duration.seconds == max(w.duration.seconds for w in detail.waits)


async def test_detail_carries_a_step_for_every_mined_step() -> None:
    detail = await get_process(TENANT, "quote_to_payment")
    assert detail is not None
    assert len(detail.steps) == 5
    assert [s.order for s in detail.steps] == [1, 2, 3, 4, 5]
    assert all(s.label for s in detail.steps)


async def test_every_duration_carries_both_a_number_and_a_sentence() -> None:
    detail = await get_process(TENANT, "quote_to_payment")
    assert detail is not None
    assert detail.total_duration.seconds > 0
    assert detail.total_duration.text.startswith("about")
    assert all(w.duration.text for w in detail.waits)


async def test_an_untouched_process_starts_at_the_bottom_rung() -> None:
    detail = await get_process(TENANT, "expenses")
    assert detail is not None
    assert detail.autonomy.level == 1
    assert detail.autonomy.level_key == "watches"
    assert detail.autonomy.can_promote is False
    assert detail.autonomy.reason


async def test_nothing_a_reader_sees_uses_jargon() -> None:
    for summary in await list_processes(TENANT):
        blob = " ".join([summary.name, summary.description, summary.slowest.text]).lower()
        assert not [w for w in JARGON if w in blob], f"{summary.id}: {blob}"


async def test_unknown_process_is_absent_rather_than_invented() -> None:
    assert await get_process(TENANT, "no-such-process") is None
