"""KGBuildSemanticEdgeModule: build semantic edges between new KG nodes and existing nodes."""

import logging
from typing import Any, Dict

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class KGBuildSemanticEdgeModule(LLMAgentModule):
    module_name = "kg_build_semantic_edge"

    INPUT_SPEC = {
        "new_node_ids": {"type": "list", "required": True},
        "struct_edge_count": {"type": "int", "required": False, "default": 0},
        "source_type": {"type": "str", "required": True},
        "source_id": {"type": "str", "required": True},
    }
    OUTPUT_SPEC = {
        "semantic_edges": {"type": "list"},
        "semantic_edge_count": {"type": "int"},
        "candidate_stats": {"type": "dict"},
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
        source_type = inputs["source_type"]
        source_id = inputs["source_id"]

        store = KGStore(config=self.config.get("neo4j"))
        try:
            builder = KGEdgeBuilder(store, config=self.config.get("edge_builder"))
            result = await builder.build_semantic_edges(
                llm_client, new_node_ids,
                source_type=source_type,
                source_id=source_id,
                struct_edge_count=struct_edge_count,
            )
        finally:
            store.close()

        logger.info(
            "KGBuildSemanticEdge: created %d semantic edges",
            result["semantic_edge_count"],
        )

        return {
            "semantic_edges": result["semantic_edges"],
            "semantic_edge_count": result["semantic_edge_count"],
            "candidate_stats": result["candidate_stats"],
            "source_type": source_type,
            "source_id": source_id,
        }

    def emit_output(self, result: Dict[str, Any]) -> AgentOutput:
        return AgentOutput(
            display_type="metrics",
            title="KG Semantic Edge Build",
            content=f"Built {result['semantic_edge_count']} semantic edges",
            data={
                "semantic_edge_count": result["semantic_edge_count"],
                "candidate_stats": result.get("candidate_stats", {}),
            },
        )
