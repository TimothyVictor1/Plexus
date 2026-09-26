from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from adapters._contract import (
    AdapterCapabilities,
    PlexusAdapter,
    SourceEvent,
    SourceItem,
    SourceRef,
    SourceSchema,
    WriteOp,
    WriteResult,
)


class _FixtureAdapter:
    id = "fixture"
    capabilities = AdapterCapabilities()

    async def backfill(self, since: datetime | None) -> AsyncIterator[SourceItem]:
        yield SourceItem(
            tenant_id="demo",
            source_id=self.id,
            external_id="1",
            kind="email",
            title="Offert",
            body="<PERSON_7f3a> bad om offert.",
            created_at=datetime.now(tz=UTC),
            raw_ref=SourceRef(source_id=self.id, external_id="1"),
        )

    async def watch(self) -> AsyncIterator[SourceEvent]:
        yield SourceEvent(
            tenant_id="demo",
            source_id=self.id,
            ref=SourceRef(source_id=self.id, external_id="1"),
            change="updated",
            ts=datetime.now(tz=UTC),
        )

    async def read(self, ref: SourceRef) -> SourceItem:
        async for item in self.backfill(None):
            return item
        raise LookupError(ref.external_id)

    async def write(self, op: WriteOp) -> WriteResult:
        return WriteResult(ok=False, message="write disabled")

    def describe_schema(self) -> SourceSchema:
        return SourceSchema(fields=[], record_types=["email"])


def test_fixture_adapter_satisfies_protocol() -> None:
    adapter = _FixtureAdapter()
    assert isinstance(adapter, PlexusAdapter)
    assert adapter.capabilities.write is False


async def test_backfill_yields_items() -> None:
    items = [item async for item in _FixtureAdapter().backfill(None)]
    assert len(items) == 1
    assert items[0].kind == "email"
