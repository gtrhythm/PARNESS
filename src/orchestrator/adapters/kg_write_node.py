"""KG write node adapter: persist nodes to Neo4j with embeddings + provenance.

Embeddings live as node properties (`n.embedding`, `n.abstract_embedding`)
and are indexed via Neo4j VECTOR INDEX. There is no separate vector store.
"""

import logging
import uuid
from typing import Any, Dict, Optional

from .base import BaseModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class KGWriteNodeModule(BaseModule):
    module_name = "kg_write_node"

    INPUT_SPEC = {
        "embedded_units": {"type": "list", "required": True},
        "duplicate_units": {"type": "list", "required": False, "default": []},
        "source_type": {"type": "str", "required": True},
        "source_id": {"type": "str", "required": True},
    }
    OUTPUT_SPEC = {
        "new_node_ids": {"type": "list"},
        "dup_appended_count": {"type": "int"},
        "total_node_count": {"type": "int"},
        "source_type": {"type": "str"},
        "source_id": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.store import KGStore
        from src.knowledge_graph.provenance import ProvenanceManager

        embedded_units = inputs["embedded_units"]
        duplicate_units = inputs.get("duplicate_units", [])
        source_type = inputs["source_type"]
        source_id = inputs["source_id"]

        store = KGStore(config=self.config.get("neo4j"))
        provenance = ProvenanceManager(store)

        new_node_ids = []
        dup_appended_count = 0

        try:
            for unit in embedded_units:
                raw_id = unit.get("id") or str(uuid.uuid4())
                try:
                    uuid.UUID(raw_id)
                    node_id = raw_id
                except (ValueError, AttributeError):
                    node_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"kg:{raw_id}"))

                chunk_text = unit.get("text", unit.get("chunk_text", ""))
                abstract_summary = unit.get("abstract_summary", "")
                content_hash = unit.get("content_hash", "")
                embedding = unit.get("embedding") or None
                abstract_embedding = unit.get("abstract_embedding") or None

                store.create_kgnode(
                    node_id=node_id,
                    chunk_text=chunk_text,
                    abstract_summary=abstract_summary,
                    content_hash=content_hash,
                    source_type=source_type,
                    source_id=source_id,
                    metadata=unit.get("metadata", {}),
                    embedding=embedding,
                    abstract_embedding=abstract_embedding,
                )

                provenance.get_or_create(
                    entity_type=source_type,
                    entity_id=source_id,
                    entity_title=unit.get("title", source_id),
                )
                provenance.add_sourced_from(
                    node_id=node_id,
                    provenance_type=source_type,
                    provenance_id=source_id,
                    provenance_path=source_type,
                    evidence_text=unit.get("evidence", "")[:500],
                    confidence=1.0,
                )

                new_node_ids.append(node_id)

            for unit in duplicate_units:
                existing_node_id = unit.get("existing_node_id", "")
                if not existing_node_id:
                    continue
                provenance.get_or_create(
                    entity_type=source_type,
                    entity_id=source_id,
                    entity_title=unit.get("title", source_id),
                )
                provenance.add_sourced_from(
                    node_id=existing_node_id,
                    provenance_type=source_type,
                    provenance_id=source_id,
                    provenance_path=source_type,
                    evidence_text=unit.get("evidence", "")[:500],
                    confidence=1.0,
                )
                dup_appended_count += 1
        finally:
            store.close()

        total_node_count = len(new_node_ids) + dup_appended_count

        logger.info(
            "KGWriteNode: %d new nodes, %d dup appended for %s/%s",
            len(new_node_ids), dup_appended_count, source_type, source_id,
        )

        return {
            "new_node_ids": new_node_ids,
            "dup_appended_count": dup_appended_count,
            "total_node_count": total_node_count,
            "source_type": source_type,
            "source_id": source_id,
        }
