"""KGNLQueryModule: answer natural-language questions over the knowledge graph."""

import logging
from typing import Any, Dict

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class KGNLQueryModule(LLMAgentModule):
    module_name = "kg_nl_query"

    INPUT_SPEC = {
        "question": {"type": "str", "required": True},
        "context": {"type": "str", "required": False, "default": ""},
        "max_hops": {"type": "int", "required": False, "default": 3},
        "top_k": {"type": "int", "required": False, "default": 20},
    }
    OUTPUT_SPEC = {
        "answer": {"type": "str"},
        "sources_used": {"type": "list"},
        "traversal_path": {"type": "list"},
        "confidence": {"type": "float"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.store import KGStore
        from src.knowledge_graph.retriever import KGRetriever
        from src.knowledge_graph.query_engine import KGQueryEngine
        from src.knowledge_graph.embedder import get_embedder

        llm_client = self._get_llm_client()

        question = inputs["question"]
        context = inputs.get("context", "")
        max_hops = inputs.get("max_hops", 3)
        top_k = inputs.get("top_k", 20)

        store = KGStore(config=self.config.get("neo4j"))
        try:
            embedder = get_embedder(self.config.get("embedder"))
            retriever = KGRetriever(store, config=self.config.get("retriever"))
            engine = KGQueryEngine(retriever, config={"embedder": embedder})

            result = await engine.answer_question(
                llm_client, question,
                context=context,
                max_hops=max_hops,
                top_k=top_k,
            )
        finally:
            store.close()

        logger.info(
            "KGNLQuery: answered '%s' with confidence %.2f",
            question[:80], result.get("confidence", 0),
        )

        return {
            "answer": result["answer"],
            "sources_used": result.get("sources_used", []),
            "traversal_path": result.get("traversal_path", []),
            "confidence": result.get("confidence", 0.0),
        }

    def emit_output(self, result: Dict[str, Any]) -> AgentOutput:
        return AgentOutput(
            display_type="text",
            title="KG NL Query",
            content=result.get("answer", "")[:500],
            data={
                "confidence": result.get("confidence", 0.0),
                "sources_used": len(result.get("sources_used", [])),
                "traversal_path": len(result.get("traversal_path", [])),
            },
        )
