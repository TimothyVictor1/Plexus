"""Neo4j graph store (spec 01).

Every query is tenant-scoped. Raw Cypher that does not bind $tenant_id is rejected before it
reaches the driver, which is the enforcement point named in the spec.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from neo4j import AsyncGraphDatabase

from core.settings import get_settings

LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,40}$")


class TenantPredicateMissingError(ValueError):
    """Cypher reached the store without a tenant predicate."""


@dataclass
class NodeUpsert:
    label: str
    key: str
    properties: dict[str, Any]


@dataclass
class EdgeUpsert:
    rel_type: str
    from_key: str
    to_key: str
    properties: dict[str, Any]


@dataclass
class GraphDelta:
    tenant_id: str
    nodes: list[NodeUpsert]
    edges: list[EdgeUpsert]


def _check_label(label: str) -> str:
    if not LABEL_RE.match(label):
        msg = f"unsafe label or relationship type: {label!r}"
        raise ValueError(msg)
    return label


class GraphStore:
    def __init__(self) -> None:
        s = get_settings()
        self._driver = AsyncGraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))

    async def close(self) -> None:
        await self._driver.close()

    async def verify(self) -> bool:
        await self._driver.verify_connectivity()
        return True

    async def init_schema(self) -> None:
        async with self._driver.session() as session:
            await session.run(
                "CREATE CONSTRAINT plexus_node_key IF NOT EXISTS "
                "FOR (n:Entity) REQUIRE (n.tenant_id, n.key) IS UNIQUE"
            )
            await session.run(
                "CREATE INDEX plexus_node_label IF NOT EXISTS"
                " FOR (n:Entity) ON (n.tenant_id, n.kind)"
            )

    async def query(
        self, tenant_id: str, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if "$tenant_id" not in cypher:
            raise TenantPredicateMissingError(cypher)
        async with self._driver.session() as session:
            result = await session.run(cypher, {"tenant_id": tenant_id, **(params or {})})
            return [dict(record) async for record in result]

    async def apply(self, delta: GraphDelta) -> dict[str, int]:
        """Apply a delta. Nodes carry their ontology label in `kind` plus the :Entity label,
        so the uniqueness constraint holds across every label."""
        counts = {"nodes": 0, "edges": 0}
        async with self._driver.session() as session:
            for node in delta.nodes:
                label = _check_label(node.label)
                await session.run(
                    f"MERGE (n:Entity {{tenant_id: $tenant_id, key: $key}}) "
                    f"SET n:{label}, n.kind = $kind, n += $props, "
                    "n.updated_at = datetime(), "
                    "n.created_at = coalesce(n.created_at, datetime())",
                    {
                        "tenant_id": delta.tenant_id,
                        "key": node.key,
                        "kind": label,
                        "props": node.properties,
                    },
                )
                counts["nodes"] += 1
            for edge in delta.edges:
                rel = _check_label(edge.rel_type)
                await session.run(
                    "MATCH (a:Entity {tenant_id: $tenant_id, key: $from_key}) "
                    "MATCH (b:Entity {tenant_id: $tenant_id, key: $to_key}) "
                    f"MERGE (a)-[r:{rel}]->(b) "
                    "SET r += $props, r.tenant_id = $tenant_id, "
                    "r.created_at = coalesce(r.created_at, datetime())",
                    {
                        "tenant_id": delta.tenant_id,
                        "from_key": edge.from_key,
                        "to_key": edge.to_key,
                        "props": edge.properties,
                    },
                )
                counts["edges"] += 1
        return counts

    async def counts(self, tenant_id: str) -> dict[str, int]:
        rows = await self.query(
            tenant_id,
            "MATCH (n:Entity {tenant_id: $tenant_id}) RETURN n.kind AS kind, count(*) AS c",
        )
        return {r["kind"]: r["c"] for r in rows}

    async def neighbourhood(self, tenant_id: str, key: str, depth: int = 1) -> dict[str, Any]:
        depth = max(1, min(depth, 3))
        rows = await self.query(
            tenant_id,
            f"MATCH (n:Entity {{tenant_id: $tenant_id, key: $key}}) "
            f"OPTIONAL MATCH p = (n)-[*1..{depth}]-(m:Entity {{tenant_id: $tenant_id}}) "
            "RETURN n, relationships(p) AS rels, nodes(p) AS ns",
            {"key": key},
        )
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        for row in rows:
            for node in (row.get("ns") or []) + ([row["n"]] if row.get("n") else []):
                props = dict(node)
                nodes[props["key"]] = {
                    "key": props["key"],
                    "kind": props.get("kind", "Record"),
                    "title": props.get("title", props["key"]),
                    "properties": {k: v for k, v in props.items() if k not in {"key", "tenant_id"}},
                }
            for rel in row.get("rels") or []:
                edges.append(
                    {
                        "type": rel.type,
                        "from": dict(rel.start_node)["key"],
                        "to": dict(rel.end_node)["key"],
                    }
                )
        unique = {(e["type"], e["from"], e["to"]): e for e in edges}
        return {"nodes": list(nodes.values()), "edges": list(unique.values())}

    async def search(self, tenant_id: str, q: str, limit: int = 40) -> list[dict[str, Any]]:
        rows = await self.query(
            tenant_id,
            "MATCH (n:Entity {tenant_id: $tenant_id}) "
            "WHERE $q = '' OR toLower(n.title) CONTAINS toLower($q) "
            "OR toLower(n.key) CONTAINS toLower($q) "
            "RETURN n.key AS key, n.kind AS kind, n.title AS title, "
            "n.confidence AS confidence, n.status AS status, n.provenance AS provenance "
            "ORDER BY n.kind, n.title LIMIT $limit",
            {"q": q, "limit": limit},
        )
        return rows


_store: GraphStore | None = None


def get_store() -> GraphStore:
    global _store
    if _store is None:
        _store = GraphStore()
    return _store
