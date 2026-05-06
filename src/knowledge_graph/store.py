"""
Neo4j graph store CRUD operations for the Knowledge Graph system.
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

_DEFAULT_URI = "bolt://localhost:7687"
_DEFAULT_USER = "neo4j"
_DEFAULT_PASSWORD = ""
_DEFAULT_DATABASE = "neo4j"


def get_neo4j_driver(config: Optional[Dict[str, Any]] = None):
    config = config or {}
    uri = config.get("uri", _DEFAULT_URI)
    user = config.get("user", _DEFAULT_USER)
    password = config.get("password", _DEFAULT_PASSWORD)
    max_retries = 10
    wait_seconds = 5

    for attempt in range(1, max_retries + 1):
        try:
            driver = GraphDatabase.driver(uri, auth=(user, password))
            driver.verify_connectivity()
            logger.info("Connected to Neo4j at %s (attempt %d)", uri, attempt)
            return driver
        except Exception as exc:
            logger.warning(
                "Neo4j connection attempt %d/%d failed: %s",
                attempt,
                max_retries,
                exc,
            )
            if attempt == max_retries:
                raise
            time.sleep(wait_seconds)


def _node_to_dict(record_node) -> Dict[str, Any]:
    return dict(record_node)


class KGStore:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._driver = None

    @property
    def driver(self):
        if self._driver is None:
            self._driver = get_neo4j_driver(self._config)
        return self._driver

    def _session(self):
        database = self._config.get("database", _DEFAULT_DATABASE)
        return self.driver.session(database=database)

    def close(self):
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def create_kgnode(
        self,
        node_id: str,
        chunk_text: str,
        abstract_summary: str,
        content_hash: str,
        source_type: str,
        source_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
        abstract_embedding: Optional[List[float]] = None,
    ) -> dict:
        now = datetime.now(timezone.utc)
        query = """
        CREATE (n:KGNode {
            id: $id,
            chunk_text: $chunk_text,
            abstract_summary: $abstract_summary,
            content_hash: $content_hash,
            source_type: $source_type,
            source_id: $source_id,
            metadata: $metadata,
            embedding: $embedding,
            abstract_embedding: $abstract_embedding,
            created_at: $now,
            updated_at: $now
        })
        RETURN n
        """
        with self._session() as session:
            result = session.run(
                query,
                id=node_id,
                chunk_text=chunk_text,
                abstract_summary=abstract_summary,
                content_hash=content_hash,
                source_type=source_type,
                source_id=source_id,
                metadata=json.dumps(metadata or {}, ensure_ascii=False),
                embedding=list(embedding) if embedding else None,
                abstract_embedding=list(abstract_embedding) if abstract_embedding else None,
                now=now,
            )
            record = result.single()
            return _node_to_dict(record["n"])

    def set_node_embeddings(
        self,
        node_id: str,
        embedding: Optional[List[float]] = None,
        abstract_embedding: Optional[List[float]] = None,
    ) -> None:
        """Update the embedding properties on an existing KGNode."""
        sets = []
        params: Dict[str, Any] = {"id": node_id}
        if embedding is not None:
            sets.append("n.embedding = $embedding")
            params["embedding"] = list(embedding)
        if abstract_embedding is not None:
            sets.append("n.abstract_embedding = $abstract_embedding")
            params["abstract_embedding"] = list(abstract_embedding)
        if not sets:
            return
        params["now"] = datetime.now(timezone.utc)
        sets.append("n.updated_at = $now")
        query = f"MATCH (n:KGNode {{id: $id}}) SET {', '.join(sets)}"
        with self._session() as session:
            session.run(query, **params)

    def find_by_content_hash(self, content_hash: str) -> Optional[dict]:
        query = """
        MATCH (n:KGNode {content_hash: $content_hash})
        RETURN n
        """
        with self._session() as session:
            result = session.run(query, content_hash=content_hash)
            record = result.single()
            if record is None:
                return None
            return _node_to_dict(record["n"])

    def find_by_source_id(
        self, source_type: str, source_id: str
    ) -> List[dict]:
        query = """
        MATCH (n:KGNode {source_type: $source_type, source_id: $source_id})
        RETURN n
        """
        with self._session() as session:
            result = session.run(
                query, source_type=source_type, source_id=source_id
            )
            return [_node_to_dict(record["n"]) for record in result]

    def get_node(self, node_id: str) -> Optional[dict]:
        query = """
        MATCH (n:KGNode {id: $id})
        RETURN n
        """
        with self._session() as session:
            result = session.run(query, id=node_id)
            record = result.single()
            if record is None:
                return None
            return _node_to_dict(record["n"])

    # Whitelist of property names that update_node is allowed to set, to
    # prevent Cypher injection via untrusted dict keys (H-01). New properties
    # must be added here explicitly.
    _UPDATABLE_NODE_PROPS = frozenset({
        "chunk_text", "abstract_summary", "metadata",
        "source_type", "source_id",
        "embedding", "abstract_embedding",
        "updated_at",
    })

    def update_node(self, node_id: str, properties: Dict[str, Any]) -> Optional[dict]:
        properties = dict(properties or {})
        properties["updated_at"] = datetime.now(timezone.utc)

        unknown = [k for k in properties if k not in self._UPDATABLE_NODE_PROPS]
        if unknown:
            raise ValueError(
                f"update_node: refusing to set non-whitelisted properties {unknown}; "
                f"add to KGStore._UPDATABLE_NODE_PROPS to allow."
            )

        set_clauses = []
        params = {"id": node_id}
        for key, value in properties.items():
            param_key = f"prop_{key}"
            set_clauses.append(f"n.{key} = ${param_key}")
            params[param_key] = value
        set_stmt = ", ".join(set_clauses)
        query = f"""
        MATCH (n:KGNode {{id: $id}})
        SET {set_stmt}
        RETURN n
        """
        with self._session() as session:
            result = session.run(query, **params)
            record = result.single()
            if record is None:
                return None
            return _node_to_dict(record["n"])

    def delete_node(self, node_id: str) -> dict:
        query = """
        MATCH (n:KGNode {id: $id})
        DETACH DELETE n
        RETURN count(n) AS deleted
        """
        with self._session() as session:
            result = session.run(query, id=node_id)
            record = result.single()
            return {"deleted": record["deleted"]}

    def create_related_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        relation_text: str,
        confidence: float,
        weight: float,
        evidence: str,
        discovered_by: str,
        walk_path: Optional[str] = None,
        visit_frequency: Optional[float] = None,
        rationale: Optional[str] = None,
    ) -> dict:
        now = datetime.now(timezone.utc)
        query = """
        MATCH (a:KGNode {id: $source_id})
        MATCH (b:KGNode {id: $target_id})
        CREATE (a)-[r:RELATED {
            relation: $relation,
            relation_text: $relation_text,
            confidence: $confidence,
            weight: $weight,
            evidence: $evidence,
            discovered_by: $discovered_by,
            walk_path: $walk_path,
            visit_frequency: $visit_frequency,
            rationale: $rationale,
            last_hit_at: $now,
            created_at: $now,
            updated_at: $now
        }]->(b)
        RETURN r
        """
        with self._session() as session:
            result = session.run(
                query,
                source_id=source_id,
                target_id=target_id,
                relation=relation,
                relation_text=relation_text,
                confidence=confidence,
                weight=weight,
                evidence=evidence,
                discovered_by=discovered_by,
                walk_path=walk_path,
                visit_frequency=visit_frequency,
                rationale=rationale,
                now=now,
            )
            record = result.single()
            if record is None:
                # MATCH didn't find one or both endpoints; this is a real error
                # (caller asked to link two nodes by id, but at least one is
                # missing). Return None so caller can decide to log/skip rather
                # than crash with `record["r"]` AttributeError.
                logger.warning(
                    "create_related_edge: MATCH failed for %s -> %s",
                    source_id, target_id,
                )
                return None
            return dict(record["r"])

    def delete_edge(
        self, source_id: str, target_id: str, relation: str
    ) -> dict:
        query = """
        MATCH (a:KGNode {id: $source_id})-[r:RELATED {relation: $relation}]->(b:KGNode {id: $target_id})
        DELETE r
        RETURN count(r) AS deleted
        """
        with self._session() as session:
            result = session.run(
                query,
                source_id=source_id,
                target_id=target_id,
                relation=relation,
            )
            record = result.single()
            return {"deleted": record["deleted"]}

    # Whitelist of edge property names that get_neighbors will filter on,
    # to prevent Cypher injection via untrusted dict keys (H-01).
    _FILTERABLE_EDGE_PROPS = frozenset({
        "relation", "relation_text", "confidence", "weight",
        "discovered_by", "phase",
    })

    def get_neighbors(
        self, node_id: str, edge_filter: Optional[Dict[str, Any]] = None
    ) -> List[dict]:
        if edge_filter:
            unknown = [k for k in edge_filter if k not in self._FILTERABLE_EDGE_PROPS]
            if unknown:
                raise ValueError(
                    f"get_neighbors: refusing to filter on non-whitelisted "
                    f"properties {unknown}; add to KGStore._FILTERABLE_EDGE_PROPS."
                )
            conditions = []
            params = {"id": node_id}
            for key, value in edge_filter.items():
                param_key = f"filter_{key}"
                conditions.append(f"r.{key} = ${param_key}")
                params[param_key] = value
            where_clause = " AND ".join(conditions)
            query = f"""
            MATCH (n:KGNode {{id: $id}})-[r:RELATED]-(m:KGNode)
            WHERE {where_clause}
            RETURN m, r
            """
        else:
            query = """
            MATCH (n:KGNode {id: $id})-[r:RELATED]-(m:KGNode)
            RETURN m, r
            """
            params = {"id": node_id}
        with self._session() as session:
            result = session.run(query, **params)
            neighbors = []
            for record in result:
                neighbors.append(
                    {"node": _node_to_dict(record["m"]), "edge": dict(record["r"])}
                )
            return neighbors

    def has_edge(self, source_id: str, target_id: str) -> bool:
        query = """
        MATCH (a:KGNode {id: $source_id})-[r:RELATED]->(b:KGNode {id: $target_id})
        RETURN count(r) > 0 AS exists
        """
        with self._session() as session:
            result = session.run(query, source_id=source_id, target_id=target_id)
            record = result.single()
            return record["exists"]

    def get_edge(self, source_id: str, target_id: str) -> Optional[dict]:
        query = """
        MATCH (a:KGNode {id: $source_id})-[r:RELATED]->(b:KGNode {id: $target_id})
        RETURN r
        """
        with self._session() as session:
            result = session.run(query, source_id=source_id, target_id=target_id)
            record = result.single()
            if record is None:
                return None
            return dict(record["r"])

    # Default cosine-similarity vector index names. Embeddings live as node
    # properties n.embedding (chunk-level) and n.abstract_embedding.
    EMBEDDING_INDEX = "kgnode_embedding_vector"
    ABSTRACT_EMBEDDING_INDEX = "kgnode_abstract_embedding_vector"

    def init_schema(self, embedding_dim: Optional[int] = None):
        if embedding_dim is None:
            embedding_dim = int((self._config or {}).get("embedding_dim", 64))
        statements = [
            "CREATE CONSTRAINT kgnode_id_unique IF NOT EXISTS FOR (n:KGNode) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT provenance_id_unique IF NOT EXISTS FOR (p:Provenance) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT kgnode_hash_unique IF NOT EXISTS FOR (n:KGNode) REQUIRE n.content_hash IS UNIQUE",
            "CREATE INDEX kgnode_source_type_idx IF NOT EXISTS FOR (n:KGNode) ON (n.source_type)",
            "CREATE INDEX kgnode_source_id_idx IF NOT EXISTS FOR (n:KGNode) ON (n.source_id)",
            "CREATE INDEX kgnode_source_composite_idx IF NOT EXISTS FOR (n:KGNode) ON (n.source_type, n.source_id)",
            "CREATE INDEX provenance_entity_type_idx IF NOT EXISTS FOR (p:Provenance) ON (p.entity_type)",
            "CREATE INDEX provenance_entity_id_idx IF NOT EXISTS FOR (p:Provenance) ON (p.entity_id)",
            "CREATE INDEX provenance_composite_idx IF NOT EXISTS FOR (p:Provenance) ON (p.entity_type, p.entity_id)",
            "CREATE INDEX kgnode_created_at_idx IF NOT EXISTS FOR (n:KGNode) ON (n.created_at)",
            "CREATE FULLTEXT INDEX kgnode_text_fulltext IF NOT EXISTS FOR (n:KGNode) ON EACH [n.chunk_text]",
            "CREATE FULLTEXT INDEX kgnode_abstract_fulltext IF NOT EXISTS FOR (n:KGNode) ON EACH [n.abstract_summary]",
            "CREATE FULLTEXT INDEX provenance_title_fulltext IF NOT EXISTS FOR (p:Provenance) ON EACH [p.entity_title]",
            (
                f"CREATE VECTOR INDEX {self.EMBEDDING_INDEX} IF NOT EXISTS "
                f"FOR (n:KGNode) ON (n.embedding) "
                f"OPTIONS {{ indexConfig: {{ `vector.dimensions`: {embedding_dim}, "
                f"`vector.similarity_function`: 'cosine' }} }}"
            ),
            (
                f"CREATE VECTOR INDEX {self.ABSTRACT_EMBEDDING_INDEX} IF NOT EXISTS "
                f"FOR (n:KGNode) ON (n.abstract_embedding) "
                f"OPTIONS {{ indexConfig: {{ `vector.dimensions`: {embedding_dim}, "
                f"`vector.similarity_function`: 'cosine' }} }}"
            ),
        ]
        with self._session() as session:
            for stmt in statements:
                session.run(stmt)
        logger.info("Neo4j schema initialized (%d statements, vector_dim=%d)",
                    len(statements), embedding_dim)

    def clear_all(self) -> dict:
        query = """
        MATCH (n)
        CALL { WITH n DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS
        RETURN count(n) AS deleted
        """
        with self._session() as session:
            result = session.run("MATCH (n:KGNode) RETURN count(n) AS c")
            node_count = result.single()["c"]
            result = session.run("MATCH ()-[r:RELATED]->() RETURN count(r) AS c")
            edge_count = result.single()["c"]
            result = session.run("MATCH (p:Provenance) RETURN count(p) AS c")
            prov_count = result.single()["c"]
            session.run(
                "MATCH (n) CALL { WITH n DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS"
            )
        return {
            "deleted_nodes": node_count,
            "deleted_edges": edge_count,
            "deleted_provenances": prov_count,
        }

    def get_stats(self) -> dict:
        with self._session() as session:
            node_result = session.run("MATCH (n:KGNode) RETURN count(n) AS c")
            node_count = node_result.single()["c"]
            edge_result = session.run("MATCH ()-[r:RELATED]->() RETURN count(r) AS c")
            edge_count = edge_result.single()["c"]
            prov_result = session.run("MATCH (p:Provenance) RETURN count(p) AS c")
            prov_count = prov_result.single()["c"]
        return {
            "nodes": node_count,
            "edges": edge_count,
            "provenances": prov_count,
        }

    def run_cypher(self, query: str, params: Optional[Dict[str, Any]] = None, **kwargs) -> List[dict]:
        if kwargs:
            params = {**(params or {}), **kwargs}
        with self._session() as session:
            result = session.run(query, parameters=params or {})
            return [record.data() for record in result]

    async def add_edge(self, source_id, target_id, relation, relation_text="",
                       confidence=0.5, weight=0.5, evidence="", discovered_by="",
                       walk_path=None, visit_frequency=None, rationale=None,
                       **kwargs):
        if self.has_edge(source_id, target_id):
            return {"skipped": True, "reason": "edge_exists"}
        return self.create_related_edge(
            source_id, target_id, relation, relation_text or relation,
            confidence, weight, evidence, discovered_by,
            walk_path=walk_path, visit_frequency=visit_frequency, rationale=rationale,
        )

    async def edge_exists(self, source_id, target_id):
        return self.has_edge(source_id, target_id)

    async def find_by_source_id(self, source_type, source_id):
        return self.find_by_source_id_sync(source_type, source_id)

    def find_by_source_id_sync(self, source_type, source_id):
        query = """
        MATCH (n:KGNode {source_type: $source_type, source_id: $source_id})
        RETURN n
        """
        with self._session() as session:
            result = session.run(query, source_type=source_type, source_id=source_id)
            return [_node_to_dict(record["n"]) for record in result]

    async def get_neighbors_async(self, node_id, edge_filter=None):
        return self.get_neighbors(node_id, edge_filter)


    # ---- Counts (used by KGRebuilder) ----
    def get_node_count(self) -> int:
        with self._session() as session:
            r = session.run("MATCH (n:KGNode) RETURN count(n) AS c").single()
            return int(r["c"]) if r else 0

    def get_edge_count(self) -> int:
        with self._session() as session:
            r = session.run("MATCH ()-[r:RELATED]->() RETURN count(r) AS c").single()
            return int(r["c"]) if r else 0

    def get_provenance_count(self) -> int:
        with self._session() as session:
            r = session.run("MATCH (p:Provenance) RETURN count(p) AS c").single()
            return int(r["c"]) if r else 0

    # ---- Vector access — backed by Neo4j 5.11+ vector indexes ----
    # Embeddings are stored on the KGNode itself as `n.embedding` and
    # `n.abstract_embedding`, indexed via VECTOR INDEX created in
    # init_schema. Adapters call `vector_search` and `get_node_embedding`;
    # they no longer need to know about a separate vector store.

    async def get_node_embedding(
        self,
        node_id: str,
        kind: str = "chunk",
    ) -> List[float]:
        """Return n.embedding (kind="chunk") or n.abstract_embedding (kind="abstract")."""
        prop = "abstract_embedding" if kind == "abstract" else "embedding"
        query = f"MATCH (n:KGNode {{id: $id}}) RETURN n.{prop} AS vec"
        with self._session() as session:
            rec = session.run(query, id=node_id).single()
            if rec is None or rec["vec"] is None:
                return []
            return list(rec["vec"])

    def delete_source(self, source_type: str, source_id: str) -> dict:
        """Cascade-delete every KGNode for a given source plus any Provenance
        that ends up orphan after that wipe. Idempotent.

        Returns counts of what was deleted. Use this when a paper / idea /
        experiment is removed from the upstream SQLite source of truth.
        """
        provenance_id = f"{source_type}_{source_id}"
        with self._session() as session:
            # 1. count what we're about to remove (for the return value)
            counts = session.run(
                """
                MATCH (n:KGNode {source_type: $source_type, source_id: $source_id})
                OPTIONAL MATCH (n)-[r:RELATED]-()
                WITH count(DISTINCT n) AS node_count, count(DISTINCT r) AS edge_count
                RETURN node_count, edge_count
                """,
                source_type=source_type, source_id=source_id,
            ).single()
            node_count = counts["node_count"] if counts else 0
            edge_count = counts["edge_count"] if counts else 0

            # 2. detach-delete the source's nodes (drops RELATED + SOURCED_FROM in one go)
            session.run(
                """
                MATCH (n:KGNode {source_type: $source_type, source_id: $source_id})
                DETACH DELETE n
                """,
                source_type=source_type, source_id=source_id,
            )

            # 3. drop the Provenance for *this* source if it now has no
            # incoming SOURCED_FROM. We only consider Provenance whose
            # entity_id matches the source we just deleted — never globally —
            # so concurrent delete_source calls on other sources can't
            # race-wipe Provenance nodes whose owning indexer hasn't yet
            # written its SOURCED_FROM edges.
            orphan_prov = session.run(
                """
                MATCH (p:Provenance {entity_id: $source_id})
                WHERE NOT EXISTS { (:KGNode)-[:SOURCED_FROM]->(p) }
                WITH p, p.id AS pid
                DETACH DELETE p
                RETURN count(pid) AS removed
                """,
                source_id=source_id,
            ).single()
            prov_removed = orphan_prov["removed"] if orphan_prov else 0

        logger.info(
            "delete_source(%s/%s): nodes=%d edges=%d orphan_provenances=%d",
            source_type, source_id, node_count, edge_count, prov_removed,
        )
        return {
            "source_type": source_type,
            "source_id": source_id,
            "provenance_id": provenance_id,
            "deleted_nodes": node_count,
            "deleted_edges": edge_count,
            "deleted_orphan_provenances": prov_removed,
        }

    async def clear_vector_indexes(self) -> None:
        """Wipe embedding properties on all KGNodes (vector index entries
        are removed automatically when their backing property is null)."""
        with self._session() as session:
            session.run(
                "MATCH (n:KGNode) "
                "REMOVE n.embedding, n.abstract_embedding"
            )

    async def vector_search(
        self,
        index_name: str,
        query_embedding: List[float],
        top_k: int = 20,
    ) -> List[dict]:
        """kNN search against a Neo4j VECTOR INDEX. Pass either
        :data:`KGStore.EMBEDDING_INDEX` or :data:`KGStore.ABSTRACT_EMBEDDING_INDEX`."""
        if not query_embedding:
            return []
        cypher = (
            "CALL db.index.vector.queryNodes($index, $top_k, $vec) "
            "YIELD node, score "
            "RETURN node.id AS id, node.id AS node_id, "
            "       node.chunk_text AS chunk_text, "
            "       node.source_type AS source_type, "
            "       node.source_id AS source_id, "
            "       score"
        )
        try:
            with self._session() as session:
                rows = session.run(
                    cypher,
                    index=index_name,
                    top_k=int(top_k),
                    vec=list(query_embedding),
                ).data()
            return [
                {
                    "id": r["id"],
                    "node_id": r["node_id"],
                    "score": r["score"],
                    "chunk_text": r.get("chunk_text", ""),
                    "source_type": r.get("source_type", ""),
                    "source_id": r.get("source_id", ""),
                }
                for r in rows
            ]
        except Exception as exc:
            # Surface the failure at WARN — silent return-[] previously hid
            # a 64-d-vs-2560-d dimensionality mismatch for hours.
            logger.warning("vector_search on %s failed: %s", index_name, exc)
            return []
