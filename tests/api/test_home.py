"""Home and its insights (redesign B7, B9)."""

from __future__ import annotations

import pytest

from core.insights import top_insights
from core.org import org_status

pytestmark = pytest.mark.integration

TENANT = "demo"


async def test_insights_are_ranked_and_capped() -> None:
    found = await top_insights(TENANT)
    assert 1 <= len(found) <= 3
    assert found[0].kind == "bottleneck", "the worst wait leads, because it costs the most time"


async def test_every_insight_points_at_something_real() -> None:
    for insight in await top_insights(TENANT):
        assert insight.text and insight.sub
        assert insight.process_id
        assert insight.health in {"smooth", "watch", "slow"}


async def test_insights_state_a_number_rather_than_a_feeling() -> None:
    for insight in await top_insights(TENANT):
        assert any(ch.isdigit() for ch in f"{insight.text} {insight.sub}")


async def test_an_empty_organisation_gets_no_insights_rather_than_invented_ones() -> None:
    assert await top_insights("no-such-org") == []


async def test_an_empty_organisation_is_offered_a_first_connection() -> None:
    status = await org_status("no-such-org")
    assert status.stage == "no_connections"
    assert status.connected_count == 0
