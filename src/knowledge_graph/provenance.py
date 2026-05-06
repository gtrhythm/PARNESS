"""
Provenance node management for the Knowledge Graph system.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ProvenanceManager:
    def __init__(self, store):
        self._store = store

    def create_provenance(
        self,
        entity_type: str,
        entity_id: str,
        entity_title: str,
        entity_metadata: Optional[Dict[str, Any]] = None,
    ) -> dict:
        prov_id = f"{entity_type}_{entity_id}"
        now = datetime.now(timezone.utc)
        query = """
        CREATE (p:Provenance {
            id: $id,
            entity_type: $entity_type,
            entity_id: $entity_id,
            entity_title: $entity_title,
            entity_metadata: $entity_metadata,
            created_at: $now,
            updated_at: $now
        })
        RETURN p
        """
        with self._store._session() as session:
            result = session.run(
                query,
                id=prov_id,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_title=entity_title,
                entity_metadata=json.dumps(entity_metadata or {}, ensure_ascii=False),
                now=now,
            )
            record = result.single()
            return dict(record["p"])

    def get_provenance(self, prov_id: str) -> Optional[dict]:
        query = """
        MATCH (p:Provenance {id: $id})
        RETURN p
        """
        with self._store._session() as session:
            result = session.run(query, id=prov_id)
            record = result.single()
            if record is None:
                return None
            return dict(record["p"])

    def find_provenance(
        self, entity_type: str, entity_id: str
    ) -> Optional[dict]:
        query = """
        MATCH (p:Provenance {entity_type: $entity_type, entity_id: $entity_id})
        RETURN p
        """
        with self._store._session() as session:
            result = session.run(
                query, entity_type=entity_type, entity_id=entity_id
            )
            record = result.single()
            if record is None:
                return None
            return dict(record["p"])

    def add_sourced_from(
        self,
        node_id: str,
        provenance_type: str,
        provenance_id: str,
        provenance_path: str,
        evidence_text: str,
        confidence: float,
    ) -> Optional[dict]:
        """Create a (:KGNode)-[:SOURCED_FROM]->(:Provenance) edge.

        `provenance_id` may be either:
        * the bare entity_id (e.g. "cs_001"), in which case we prefix it with
          provenance_type to derive the Provenance.id, OR
        * the already-prefixed Provenance.id (e.g. "paper_cs_001").
        We detect the latter to stay backwards-compatible with old call sites.
        Returns None if either MATCH fails (instead of crashing on
        record["r"] when result is None).
        """
        prefix = f"{provenance_type}_"
        full_provenance_id = (
            provenance_id if provenance_id.startswith(prefix)
            else prefix + provenance_id
        )

        now = datetime.now(timezone.utc)
        query = """
        MATCH (n:KGNode {id: $node_id})
        MATCH (p:Provenance {id: $full_provenance_id})
        CREATE (n)-[r:SOURCED_FROM {
            provenance_type: $provenance_type,
            provenance_id: $full_provenance_id,
            provenance_path: $provenance_path,
            evidence_text: $evidence_text,
            confidence: $confidence,
            created_at: $now
        }]->(p)
        RETURN r
        """
        with self._store._session() as session:
            result = session.run(
                query,
                node_id=node_id,
                provenance_type=provenance_type,
                full_provenance_id=full_provenance_id,
                provenance_path=provenance_path,
                evidence_text=evidence_text,
                confidence=confidence,
                now=now,
            )
            record = result.single()
            if record is None:
                logger.warning(
                    "add_sourced_from: MATCH failed (node=%s, provenance=%s)",
                    node_id, full_provenance_id,
                )
                return None
            return dict(record["r"])

    def get_node_provenances(self, node_id: str) -> List[dict]:
        query = """
        MATCH (n:KGNode {id: $node_id})-[r:SOURCED_FROM]->(p:Provenance)
        RETURN r, p
        """
        with self._store._session() as session:
            result = session.run(query, node_id=node_id)
            provenances = []
            for record in result:
                provenances.append({"edge": dict(record["r"]), "provenance": dict(record["p"])})
            return provenances

    def get_provenance_nodes(self, prov_id: str) -> List[dict]:
        query = """
        MATCH (n:KGNode)-[r:SOURCED_FROM]->(p:Provenance {id: $prov_id})
        RETURN n, r
        """
        with self._store._session() as session:
            result = session.run(query, prov_id=prov_id)
            nodes = []
            for record in result:
                nodes.append({"node": dict(record["n"]), "edge": dict(record["r"])})
            return nodes

    def delete_provenance(self, prov_id: str) -> dict:
        query = """
        MATCH (p:Provenance {id: $prov_id})
        OPTIONAL MATCH (n:KGNode)-[sf:SOURCED_FROM]->(p)
        WITH p, n, sf, size((n)-[:SOURCED_FROM]->()) AS source_count
        FOREACH (_ IN CASE WHEN source_count = 1 THEN [1] ELSE [] END |
            DETACH DELETE n
        )
        WITH DISTINCT p
        DETACH DELETE p
        """
        with self._store._session() as session:
            count_result = session.run(
                "MATCH (n:KGNode)-[:SOURCED_FROM]->(p:Provenance {id: $prov_id}) "
                "WHERE size((n)-[:SOURCED_FROM]->()) = 1 "
                "RETURN count(n) AS orphan_count",
                prov_id=prov_id,
            )
            orphan_count = count_result.single()["orphan_count"]
            session.run(query, prov_id=prov_id)
        return {"provenance_id": prov_id, "orphan_nodes_deleted": orphan_count}

    def get_or_create(
        self,
        entity_type: str,
        entity_id: str,
        entity_title: str,
        entity_metadata: Optional[Dict[str, Any]] = None,
    ) -> dict:
        existing = self.find_provenance(entity_type, entity_id)
        if existing is not None:
            return existing
        return self.create_provenance(entity_type, entity_id, entity_title, entity_metadata)
