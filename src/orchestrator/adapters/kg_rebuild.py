"""KG full rebuild adapter."""

import logging
from typing import Any, Dict, List, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class KGRebuildModule(LLMAgentModule):
    module_name = "kg_rebuild"

    INPUT_SPEC = {
        "db_paths": {"type": "dict", "required": False, "default": {}},
        "clear_existing": {"type": "bool", "required": False, "default": False},
        "cache_extraction": {"type": "bool", "required": False, "default": True},
    }
    OUTPUT_SPEC = {
        "total_nodes": {"type": "int"},
        "total_edges": {"type": "int"},
        "total_provenances": {"type": "int"},
        "duration_seconds": {"type": "float"},
        "errors": {"type": "list"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.rebuild import KGRebuilder
        from src.knowledge_graph.store import KGStore

        llm_client = self._get_llm_client()
        db_paths = inputs.get("db_paths", {})
        clear_existing = inputs.get("clear_existing", False)
        cache_extraction = inputs.get("cache_extraction", True)

        store = KGStore(config=self.config.get("neo4j"))
        try:
            rebuilder = KGRebuilder(store, self.config)
            result = await rebuilder.rebuild_all(llm_client, db_paths, clear_existing, cache_extraction)
        finally:
            store.close()

        logger.info(
            "KGRebuild: %d nodes, %d edges, %d provenances in %.1fs (%d errors)",
            result.get("total_nodes", 0),
            result.get("total_edges", 0),
            result.get("total_provenances", 0),
            result.get("duration_seconds", 0.0),
            len(result.get("errors", [])),
        )

        return {
            "total_nodes": result.get("total_nodes", 0),
            "total_edges": result.get("total_edges", 0),
            "total_provenances": result.get("total_provenances", 0),
            "duration_seconds": result.get("duration_seconds", 0.0),
            "errors": result.get("errors", []),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        return AgentOutput(
            display_type="metrics",
            title="KG Rebuild",
            content=f"Nodes: {result.get('total_nodes', 0)}, "
                    f"Edges: {result.get('total_edges', 0)}, "
                    f"Provenances: {result.get('total_provenances', 0)}",
            data={
                "total_nodes": result.get("total_nodes", 0),
                "total_edges": result.get("total_edges", 0),
                "total_provenances": result.get("total_provenances", 0),
                "duration_seconds": result.get("duration_seconds", 0.0),
                "errors": len(result.get("errors", [])),
            },
            render_hints={"layout": "grid", "columns": 3},
        )
