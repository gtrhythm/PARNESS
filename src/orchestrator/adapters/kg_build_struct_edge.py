"""KG build structural edge adapter: structural edge construction from node IDs."""

import logging
from typing import Any, Dict, Optional

from .base import BaseModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class KGBuildStructEdgeModule(BaseModule):
    module_name = "kg_build_struct_edge"

    INPUT_SPEC = {
        "new_node_ids": {"type": "list", "required": True},
        "source_type": {"type": "str", "required": True},
        "source_id": {"type": "str", "required": True},
    }
    OUTPUT_SPEC = {
        "struct_edges": {"type": "list"},
        "struct_edge_count": {"type": "int"},
        "source_type": {"type": "str"},
        "source_id": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.edge_builder import KGEdgeBuilder
        from src.knowledge_graph.store import KGStore

        new_node_ids = inputs["new_node_ids"]
        source_type = inputs["source_type"]
        source_id = inputs["source_id"]

        neo4j_config = self.config.get("neo4j")
        store = KGStore(config=neo4j_config)

        try:
            builder = KGEdgeBuilder(store, config=self.config)
            struct_edges = await builder.build_structural_edges(
                new_node_ids, source_type, source_id
            )
        finally:
            store.close()

        logger.info(
            "KGBuildStructEdge: %d structural edges for %s/%s",
            len(struct_edges), source_type, source_id,
        )

        return {
            "struct_edges": struct_edges,
            "struct_edge_count": len(struct_edges),
            "source_type": source_type,
            "source_id": source_id,
        }
