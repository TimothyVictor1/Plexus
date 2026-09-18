"""The single write path to customer systems (spec 05).

Phase 0: placeholder that exists so the architecture tests can name it. Phase 3 implements
plan -> simulate -> verify -> approve/auto -> execute -> record. Nothing else in the codebase may
import an adapter's `write` or the PII boundary's `restore`.
"""

from __future__ import annotations


class WritePathNotImplementedError(RuntimeError):
    """Raised until Phase 3 lands. Guarantees no write can happen before the pipeline exists."""


async def execute(*_args: object, **_kwargs: object) -> None:
    raise WritePathNotImplementedError("the action pipeline is implemented in Phase 3 (spec 05)")
