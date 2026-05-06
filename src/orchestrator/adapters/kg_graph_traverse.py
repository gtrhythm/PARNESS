"""KGGraphTraverseModule: traverse subgraph starting from given node IDs."""

import logging
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class KGGraphTraverseModule(BaseModule):
    module_name = "kg_graph_traverse"

    INPUT_SPEC = {
        "node_ids": {"type": "list", "required": True},
        "max_hops": {"type": "int", "required": False, "default": 3},
        "edge_filter": {"type": "dict", "required": False, "default": {}},
        "include_provenance": {"type": "bool", "required": False, "default": True},
    }
    OUTPUT_SPEC = {
        "nodes": {"type": "list"},
        "edges": {"type": "list"},
        "provenances": {"type": "list"},
        "hop_reached": {"type": "int"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.retriever import KGRetriever
        from src.knowledge_graph.store import KGStore

        node_ids = inputs["node_ids"]
        max_hops = inputs.get("max_hops", 3)
        edge_filter = inputs.get("edge_filter", {})
        include_provenance = inputs.get("include_provenance", True)

        store = KGStore(config=self.config.get("neo4j"))
        try:
            retriever = KGRetriever(store, config=self.config.get("retriever"))
            result = await retriever.traverse_subgraph(
                node_ids,
                max_hops=max_hops,
                edge_filter=edge_filter if edge_filter else None,
                include_provenance=include_provenance,
            )
        finally:
            store.close()

        logger.info(
            "KGGraphTraverse: %d nodes, %d edges, hop_reached=%d",
            len(result["nodes"]),
            len(result["edges"]),
            result["hop_reached"],
        )

        return {
            "nodes": result["nodes"],
            "edges": result["edges"],
            "provenances": result["provenances"],
            "hop_reached": result["hop_reached"],
        }
