"""KG CRUD operations adapter."""

import asyncio
import logging
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class KGCRUDModule(BaseModule):
    module_name = "kg_crud"

    INPUT_SPEC = {
        "operation": {"type": "str", "required": True},
        "node_id": {"type": "str", "required": False, "default": ""},
        "data": {"type": "dict", "required": False, "default": {}},
        "filters": {"type": "dict", "required": False, "default": {}},
    }
    OUTPUT_SPEC = {
        "result": {"type": "dict"},
        "success": {"type": "bool"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.store import KGStore
        from src.knowledge_graph.provenance import ProvenanceManager

        operation = inputs["operation"]
        node_id = inputs.get("node_id", "")
        data = inputs.get("data", {}) or {}
        filters = inputs.get("filters", {}) or {}

        store = KGStore(config=self.config.get("neo4j"))
        prov = ProvenanceManager(store)

        def _create_node():
            return store.create_kgnode(
                node_id=data.get("id") or data.get("node_id", ""),
                chunk_text=data.get("chunk_text", data.get("text", "")),
                abstract_summary=data.get("abstract_summary", ""),
                content_hash=data.get("content_hash", ""),
                source_type=data.get("source_type", ""),
                source_id=data.get("source_id", ""),
                metadata=data.get("metadata", {}),
            )

        def _create_edge():
            return store.create_related_edge(
                source_id=data.get("source_id", ""),
                target_id=data.get("target_id", ""),
                relation=data.get("relation", "RELATED_TO"),
                relation_text=data.get("relation_text", ""),
                confidence=float(data.get("confidence", 0.5)),
                weight=float(data.get("weight", 0.5)),
                evidence=data.get("evidence", ""),
                discovered_by=data.get("discovered_by", "manual"),
            )

        def _delete_edge():
            return store.delete_edge(
                source_id=data.get("source_id", ""),
                target_id=data.get("target_id", ""),
                relation=data.get("relation", "RELATED_TO"),
            )

        dispatch = {
            "create_node": _create_node,
            "read_node": lambda: store.get_node(node_id),
            "update_node": lambda: store.update_node(node_id, data),
            "delete_node": lambda: store.delete_node(node_id),
            "create_edge": _create_edge,
            "delete_edge": _delete_edge,
            "read_provenance": lambda: prov.get_node_provenances(node_id),
            "get_stats": lambda: store.get_stats(),
        }

        handler = dispatch.get(operation)
        if handler is None:
            logger.warning("KGCRUD: unknown operation '%s'", operation)
            store.close()
            return {"result": {}, "success": False}

        try:
            result = handler()
            if asyncio.iscoroutine(result):
                result = await result
            logger.info("KGCRUD: operation='%s' success=True", operation)
            return {"result": result, "success": True}
        except Exception as e:
            logger.error("KGCRUD: operation='%s' failed: %s", operation, e)
            return {"result": {}, "success": False}
        finally:
            store.close()
