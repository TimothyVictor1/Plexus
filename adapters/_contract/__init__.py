"""Adapter base classes, schemas, and the conformance suite (spec 01, spec 08)."""

from adapters._contract.base import (
    ActorRef,
    AdapterCapabilities,
    FieldSpec,
    PlexusAdapter,
    SourceEvent,
    SourceItem,
    SourceRef,
    SourceSchema,
    WriteOp,
    WriteResult,
)

__all__ = [
    "ActorRef",
    "AdapterCapabilities",
    "FieldSpec",
    "PlexusAdapter",
    "SourceEvent",
    "SourceItem",
    "SourceRef",
    "SourceSchema",
    "WriteOp",
    "WriteResult",
]
