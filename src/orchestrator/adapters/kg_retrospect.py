"""KGRetrospectModule: retrospect edges between neighbor-of-neighbor nodes in the KG."""

import logging
from typing import Any, Dict

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class KGRetrospectModule(LLMAgentModule):
    module_name = "kg_retrospect"

    INPUT_SPEC = {
        "new_node_ids": {"type": "list", "required": True},
        "struct_edge_count": {"type": "int", "required": False, "default": 0},
        "semantic_edge_count": {"type": "int", "required": False, "default": 0},
        "walk_edge_count": {"type": "int", "required": False, "default": 0},
        "source_type": {"type": "str", "required": True},
        "source_id": {"type": "str", "required": True},
    }
    OUTPUT_SPEC = {
        "retrospect_edges": {"type": "list"},
        "retrospect_edge_count": {"type": "int"},
        "candidate_pair_count": {"type": "int"},
        "source_type": {"type": "str"},
        "source_id": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.store import KGStore
        from src.knowledge_graph.edge_builder import KGEdgeBuilder

        llm_client = self._get_llm_client()

        new_node_ids = inputs["new_node_ids"]
        struct_edge_count = inputs.get("struct_edge_count", 0)
        semantic_edge_count = inputs.get("semantic_edge_count", 0)
        walk_edge_count = inputs.get("walk_edge_count", 0)
        source_type = inputs["source_type"]
        source_id = inputs["source_id"]

        store = KGStore(config=self.config.get("neo4j"))
        try:
            builder = KGEdgeBuilder(store, config=self.config.get("edge_builder"))
            edges = await builder.retrospect_edges(
                llm_client, new_node_ids,
                struct_edge_count=struct_edge_count,
                semantic_edge_count=semantic_edge_count,
                walk_edge_count=walk_edge_count,
            )
        finally:
            store.close()

        logger.info(
            "KGRetrospect: created %d retrospect edges",
            len(edges),
        )

        return {
            "retrospect_edges": edges,
            "retrospect_edge_count": len(edges),
            "candidate_pair_count": len(edges),
            "source_type": source_type,
            "source_id": source_id,
        }

    def emit_output(self, result: Dict[str, Any]) -> AgentOutput:
        return AgentOutput(
            display_type="metrics",
            title="KG Retrospect",
            content=f"Created {result['retrospect_edge_count']} retrospect edges",
            data={
                "retrospect_edge_count": result["retrospect_edge_count"],
                "candidate_pair_count": result["candidate_pair_count"],
            },
        )
