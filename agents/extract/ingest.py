"""Ingestion: fixtures to tokenised documents, graph nodes and events (specs 01, 02, 06).

Every item passes the PII Boundary before it is stored anywhere, so neither Postgres nor Neo4j
ever holds a real personal value. The vault is the only place those live.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from adapters._contract.base import ActorRef, SourceRef
from core.db.pool import tenant_conn
from core.events.model import ObjectRef, PlexusEvent, write_events
from core.graph.store import EdgeUpsert, GraphDelta, GraphStore, NodeUpsert
from core.pii.boundary import Boundary, learn_names
from core.pii.vault import TokenVault


class Ingestor:
    def __init__(self, boundary: Boundary, vault: TokenVault, store: GraphStore | None) -> None:
        self.boundary = boundary
        self.vault = vault
        # A deployment may have no graph store. Documents, the vault and the event log still
        # get written, which is what every screen reads from; only the map is skipped.
        self.store = store

    async def ingest(
        self,
        tenant_id: str,
        source_id: str,
        items: list[dict[str, Any]],
        connection_id: str | None = None,
    ) -> dict[str, int]:
        documents = 0
        nodes: list[NodeUpsert] = []
        edges: list[EdgeUpsert] = []
        events: list[PlexusEvent] = []

        for item in items:
            body_tok, tmap = self.boundary.tokenize_text(
                str(item.get("body", "")), tenant_id=tenant_id
            )
            title_tok, tmap = self.boundary.tokenize_text(
                str(item.get("title") or item.get("subject") or ""),
                tenant_id=tenant_id,
                token_map=tmap,
            )
            structured = {
                k: v
                for k, v in item.items()
                if k not in {"body", "title", "subject", "ts", "objects", "verb", "case"}
            }
            structured_tok, tmap = self.boundary.tokenize(
                structured, tenant_id=tenant_id, token_map=tmap
            )

            for token, entity_type, value in tmap.items_for_vault():
                await self.vault.put(tenant_id, token, entity_type, value)

            actor_email = str(item.get("from") or item.get("assignee") or "system")
            actor_token, tmap = self.boundary.tokenize_text(
                actor_email, tenant_id=tenant_id, token_map=tmap
            )
            for token, entity_type, value in tmap.items_for_vault():
                await self.vault.put(tenant_id, token, entity_type, value)

            ts: datetime = item["ts"]
            external_id = str(item["external_id"])
            ref = SourceRef(source_id=source_id, external_id=external_id)

            async with tenant_conn(tenant_id) as conn:
                await conn.execute(
                    "INSERT INTO documents (id, tenant_id, source_id, external_id, kind, title,"
                    " body_tokenised, structured, actors, source_ref, created_at, connection_id)"
                    " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)"
                    " ON CONFLICT (tenant_id, source_id, external_id) DO UPDATE"
                    " SET body_tokenised = EXCLUDED.body_tokenised, title = EXCLUDED.title,"
                    " connection_id = EXCLUDED.connection_id",
                    str(uuid.uuid4()),
                    tenant_id,
                    source_id,
                    external_id,
                    str(item.get("kind", "record")),
                    title_tok,
                    body_tok,
                    json.dumps(structured_tok, default=str),
                    json.dumps([{"token": actor_token, "kind": "person"}]),
                    json.dumps(ref.model_dump()),
                    ts,
                    connection_id,
                )
            documents += 1

            doc_key = f"{source_id}:{external_id}"
            nodes.append(
                NodeUpsert(
                    label={"email": "Artifact", "task": "Record", "file": "Artifact"}.get(
                        str(item.get("kind")), "Record"
                    ),
                    key=doc_key,
                    properties={
                        "title": title_tok[:200] or external_id,
                        "source": source_id,
                        "record_type": str(item.get("kind", "record")),
                        "status": "confirmed",
                        "confidence": 1.0,
                        "valid_from": ts.isoformat(),
                        "provenance": json.dumps([ref.model_dump()]),
                    },
                )
            )
            nodes.append(
                NodeUpsert(
                    label="Person",
                    key=actor_token,
                    properties={
                        "title": actor_token,
                        "status": "proposed",
                        "confidence": 0.85,
                        "provenance": json.dumps([ref.model_dump()]),
                    },
                )
            )
            edges.append(EdgeUpsert("PRODUCED", actor_token, doc_key, {"confidence": 1.0}))

            case = str(item.get("case", ""))
            if case:
                case_key = f"case:{case}"
                nodes.append(
                    NodeUpsert(
                        label="Project",
                        key=case_key,
                        properties={"title": case, "status": "confirmed", "confidence": 1.0},
                    )
                )
                edges.append(EdgeUpsert("MENTIONS", doc_key, case_key, {}))

            for token in tmap.tokens:
                if token.startswith("<ORG_"):
                    nodes.append(
                        NodeUpsert(
                            label="Organisation",
                            key=token,
                            properties={
                                "title": token,
                                "status": "proposed",
                                "confidence": 0.9,
                                "provenance": json.dumps([ref.model_dump()]),
                            },
                        )
                    )
                    edges.append(EdgeUpsert("MENTIONS", doc_key, token, {}))

            verb = str(item.get("verb", "created"))
            objects = [
                ObjectRef(object_type=o, object_id=case or external_id)
                for o in item.get("objects", ["record"])
            ]
            objects.append(ObjectRef(object_type="doc", object_id=external_id))
            # Deterministic id: re-ingesting the same item updates rather than duplicates.
            event_key = f"{tenant_id}|{source_id}|{external_id}|{verb}"
            event_uuid = str(uuid.UUID(hashlib.sha256(event_key.encode()).hexdigest()[:32]))
            events.append(
                PlexusEvent(
                    event_id=event_uuid,
                    tenant_id=tenant_id,
                    ts=ts,
                    actor=ActorRef(token=actor_token, kind="person"),
                    verb=verb,
                    objects=objects,
                    source=ref,
                    attributes=dict(item.get("attributes", {})),
                )
            )

        if self.store is not None:
            await self.store.apply(GraphDelta(tenant_id=tenant_id, nodes=nodes, edges=edges))
        await write_events(tenant_id, events)
        return {
            "documents": documents,
            "nodes": len(nodes),
            "edges": len(edges),
            "events": len(events),
        }


async def seed_gazetteer(
    tenant_id: str, people: list[dict[str, str]], customers: list[dict[str, str]]
) -> None:
    """Adapter metadata gives the boundary its person gazetteer (spec 06, OQ-06-1).

    Persisted so every process that loads the boundary sees the same names, not just the one
    that happened to run ingestion.
    """
    names = [p["name"] for p in people] + [c["contact"] for c in customers]
    learn_names(tenant_id, names)
    async with tenant_conn(tenant_id) as conn:
        await conn.executemany(
            "INSERT INTO pii_gazetteer (tenant_id, name) VALUES ($1,$2)"
            " ON CONFLICT (tenant_id, name) DO NOTHING",
            [(tenant_id, n) for n in names],
        )


async def load_gazetteer(tenant_id: str) -> int:
    """Called at API startup so the boundary is complete in every process."""
    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch("SELECT name FROM pii_gazetteer WHERE tenant_id=$1", tenant_id)
    learn_names(tenant_id, [r["name"] for r in rows])
    return len(rows)


async def load_all_gazetteers() -> int:
    """Load every org's gazetteer at startup. No tenant id is hardcoded anywhere."""
    async with tenant_conn("bootstrap") as conn:
        tenants = await conn.fetch("SELECT id FROM tenants")
    return sum([await load_gazetteer(row["id"]) for row in tenants])
