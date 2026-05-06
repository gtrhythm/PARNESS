"""KGRandomWalkModule: discover remote KG relations via random walks."""

import logging
from typing import Any, Dict

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class KGRandomWalkModule(LLMAgentModule):
    module_name = "kg_random_walk"

    INPUT_SPEC = {
        "new_node_ids": {"type": "list", "required": True},
        "semantic_edge_count": {"type": "int", "required": False, "default": 0},
        "source_type": {"type": "str", "required": True},
        "source_id": {"type": "str", "required": True},
    }
    OUTPUT_SPEC = {
        "walk_edges": {"type": "list"},
        "walk_edge_count": {"type": "int"},
        "walk_stats": {"type": "dict"},
        "source_type": {"type": "str"},
        "source_id": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.store import KGStore
        from src.knowledge_graph.random_walk import KGRandomWalker

        llm_client = self._get_llm_client()

        new_node_ids = inputs["new_node_ids"]
        semantic_edge_count = inputs.get("semantic_edge_count", 0)
        source_type = inputs["source_type"]
        source_id = inputs["source_id"]

        store = KGStore(config=self.config.get("neo4j"))
        try:
            walker = KGRandomWalker(store, config=self.config.get("random_walk"))
            result = await walker.discover_remote_relations(
                llm_client, new_node_ids,
                source_type=source_type,
                source_id=source_id,
                semantic_edge_count=semantic_edge_count,
            )
        finally:
            store.close()

        logger.info(
            "KGRandomWalk: discovered %d walk edges",
            result["walk_edge_count"],
        )

        return {
            "walk_edges": result["walk_edges"],
            "walk_edge_count": result["walk_edge_count"],
            "walk_stats": result["walk_stats"],
            "source_type": source_type,
            "source_id": source_id,
        }

    def emit_output(self, result: Dict[str, Any]) -> AgentOutput:
        return AgentOutput(
            display_type="metrics",
            title="KG Random Walk",
            content=f"Discovered {result['walk_edge_count']} walk edges",
            data={
                "walk_edge_count": result["walk_edge_count"],
                "walk_stats": result.get("walk_stats", {}),
            },
        )
