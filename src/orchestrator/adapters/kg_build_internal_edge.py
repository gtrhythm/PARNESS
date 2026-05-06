"""KG build internal edge adapter: LLM-powered intra-source relation discovery."""

import logging
from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class KGBuildInternalEdgeModule(LLMAgentModule):
    module_name = "kg_build_internal_edge"

    INPUT_SPEC = {
        "units": {"type": "list", "required": True},
        "source_type": {"type": "str", "required": True},
        "source_id": {"type": "str", "required": True},
    }
    OUTPUT_SPEC = {
        "relations": {"type": "list"},
        "relation_count": {"type": "int"},
        "source_type": {"type": "str"},
        "source_id": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.edge_builder import KGEdgeBuilder
        from src.knowledge_graph.store import KGStore

        llm_client = self._get_llm_client()
        units = inputs["units"]
        source_type = inputs["source_type"]
        source_id = inputs["source_id"]

        neo4j_config = self.config.get("neo4j")
        store = KGStore(config=neo4j_config)

        try:
            builder = KGEdgeBuilder(store, config=self.config)
            relations = await builder.evaluate_internal_relations(
                llm_client, units, source_type, source_id
            )
        finally:
            store.close()

        logger.info(
            "KGBuildInternalEdge: %d relations for %s/%s",
            len(relations), source_type, source_id,
        )

        return {
            "relations": relations,
            "relation_count": len(relations),
            "source_type": source_type,
            "source_id": source_id,
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        relation_count = result.get("relation_count", 0)
        return AgentOutput(
            display_type="metrics",
            title="KG Build Internal Edge",
            content=f"Discovered {relation_count} internal relations",
            data={"relation_count": relation_count},
        )
