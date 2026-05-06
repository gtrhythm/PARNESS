"""KG idea synthesis adapter."""

import logging
from typing import Any, Dict, List, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class KGSynthesizeModule(LLMAgentModule):
    module_name = "kg_synthesize"

    INPUT_SPEC = {
        "seed_idea": {"type": "str", "required": True},
        "max_depth": {"type": "int", "required": False, "default": 5},
        "strategy": {"type": "str", "required": False, "default": "cross_domain"},
    }
    OUTPUT_SPEC = {
        "synthesized_ideas": {"type": "list"},
        "source_paths": {"type": "list"},
        "idea_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.query_engine import KGQueryEngine
        from src.knowledge_graph.retriever import KGRetriever
        from src.knowledge_graph.store import KGStore
        from src.knowledge_graph.embedder import get_embedder

        llm_client = self._get_llm_client()
        seed_idea = inputs["seed_idea"]
        max_depth = inputs.get("max_depth", 5)
        strategy = inputs.get("strategy", "cross_domain")

        store = KGStore(config=self.config.get("neo4j"))
        embedder = get_embedder(self.config.get("embedder"))
        try:
            retriever = KGRetriever(store, config=self.config.get("retriever"))
            engine = KGQueryEngine(retriever, config={"embedder": embedder})
            result = await engine.synthesize_ideas(llm_client, seed_idea, max_depth, strategy)
        finally:
            store.close()

        ideas = result.get("synthesized_ideas", [])
        paths = result.get("source_paths", [])

        logger.info(
            "KGSynthesize: %d ideas from %d source paths (strategy=%s, depth=%d)",
            len(ideas), len(paths), strategy, max_depth,
        )

        return {
            "synthesized_ideas": ideas,
            "source_paths": paths,
            "idea_count": len(ideas),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        ideas = result.get("synthesized_ideas", [])
        rows = [[i.get("title", "")[:80], i.get("category", ""), i.get("score", "")]
                for i in ideas[:50]]
        return AgentOutput(
            display_type="table",
            title="KG Synthesized Ideas",
            data={"headers": ["Title", "Category", "Score"], "rows": rows},
            render_hints={},
        )
