from __future__ import annotations

import pytest

from core.action import executor


async def test_executor_refuses_until_phase_3() -> None:
    with pytest.raises(executor.WritePathNotImplementedError):
        await executor.execute()
