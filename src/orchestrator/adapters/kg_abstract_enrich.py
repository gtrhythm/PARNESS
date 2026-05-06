"""KG abstract enrichment adapter."""

import logging
from typing import Any, Dict, List, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class KGAbstractEnrichModule(LLMAgentModule):
    module_name = "kg_abstract_enrich"

    INPUT_SPEC = {
        "abstract": {"type": "str", "required": True},
        "top_k": {"type": "int", "required": False, "default": 10},
        "max_hops": {"type": "int", "required": False, "default": 3},
    }
    OUTPUT_SPEC = {
        "enriched_context": {"type": "str"},
        "related_methods": {"type": "list"},
        "related_experiments": {"type": "list"},
        "related_code": {"type": "list"},
        "source_papers": {"type": "list"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.query_engine import KGQueryEngine
        from src.knowledge_graph.retriever import KGRetriever
        from src.knowledge_graph.store import KGStore
        from src.knowledge_graph.embedder import get_embedder

        llm_client = self._get_llm_client()
        abstract = inputs["abstract"]
        top_k = inputs.get("top_k", 10)
        max_hops = inputs.get("max_hops", 3)

        store = KGStore(config=self.config.get("neo4j"))
        embedder = get_embedder(self.config.get("embedder"))
        try:
            retriever = KGRetriever(store, config=self.config.get("retriever"))
            engine = KGQueryEngine(retriever, config={"embedder": embedder})
            result = await engine.enrich_abstract(llm_client, abstract, top_k, max_hops)
        finally:
            store.close()

        logger.info(
            "KGAbstractEnrich: enriched abstract, %d methods, %d experiments, %d code, %d papers",
            len(result.get("related_methods", [])),
            len(result.get("related_experiments", [])),
            len(result.get("related_code", [])),
            len(result.get("source_papers", [])),
        )

        return {
            "enriched_context": result.get("enriched_context", ""),
            "related_methods": result.get("related_methods", []),
            "related_experiments": result.get("related_experiments", []),
            "related_code": result.get("related_code", []),
            "source_papers": result.get("source_papers", []),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        return AgentOutput(
            display_type="metrics",
            title="KG Abstract Enrich",
            content=f"Methods: {len(result.get('related_methods', []))}, "
                    f"Experiments: {len(result.get('related_experiments', []))}, "
                    f"Code: {len(result.get('related_code', []))}, "
                    f"Papers: {len(result.get('source_papers', []))}",
            data={
                "related_methods": len(result.get("related_methods", [])),
                "related_experiments": len(result.get("related_experiments", [])),
                "related_code": len(result.get("related_code", [])),
                "source_papers": len(result.get("source_papers", [])),
            },
            render_hints={"layout": "grid", "columns": 4},
        )
