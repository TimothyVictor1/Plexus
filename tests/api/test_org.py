"""Org and onboarding stage (redesign B1)."""

from __future__ import annotations

import pytest

from core.org.service import OrgStatus

pytestmark = pytest.mark.integration


async def test_org_has_a_name_and_demo_flag() -> None:
    from core.org import get_org

    org = await get_org("demo")
    assert org is not None
    assert org.display_name
    assert org.is_demo is True


async def test_status_is_ready_for_the_seeded_demo() -> None:
    from core.org import org_status

    status: OrgStatus = await org_status("demo")
    assert status.stage == "ready"
    assert status.connected_count > 0
    assert status.process_count == 6


async def test_unknown_org_has_no_connections() -> None:
    from core.org import org_status

    status = await org_status("no-such-org")
    assert status.stage == "no_connections"
    assert status.connected_count == 0
    assert status.process_count == 0
