import logging
from typing import Any, Dict

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class PaperCodeRetrievalModule(LLMAgentModule):
    module_name = "paper_code_retrieval"

    INPUT_SPEC = {
        "query": {"type": "str", "required": False, "default": ""},
        "idea_description": {"type": "str", "required": False, "default": ""},
        "top_k": {"type": "int", "required": False, "default": 5},
        "filters": {"type": "dict", "required": False, "default": None},
        "generate_guide": {"type": "bool", "required": False, "default": False},
    }
    OUTPUT_SPEC = {
        "success": {"type": "bool"},
        "results": {"type": "list"},
        "result_count": {"type": "int"},
        "implementation_guide": {"type": "str"},
        "_query": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.code_analyzer.retrieval_service import PaperCodeRetrievalService
        query = inputs.get("query", inputs.get("idea_description", ""))
        top_k = inputs.get("top_k", self.config.get("top_k", 5))
        filters = inputs.get("filters")
        generate_guide = inputs.get("generate_guide", False)

        if not query:
            return {
                "success": False,
                "error": "Missing required input: query or idea_description",
                "results": [],
            }

        llm_client = self._get_llm_client()

        service = PaperCodeRetrievalService(llm_client=llm_client)

        results = await service.find_similar_implementations(
            query=query,
            top_k=top_k,
            filters=filters,
        )

        guide = ""
        if generate_guide and results:
            guide = await service.get_implementation_guide(query, top_k=top_k)

        return {
            "success": True,
            "results": results,
            "result_count": len(results),
            "implementation_guide": guide,
            "_query": query,
        }

    def emit_output(self, result):
        if not result.get("success", False):
            return None
        results = result.get("results", [])
        query = result.get("_query", "")
        guide = result.get("implementation_guide", "")
        if self.has_progress_reporter:
            self._reporter.emit_output(AgentOutput(
                display_type="metrics",
                title="Code Retrieval Results",
                content=f"Found {len(results)} similar implementations",
                data={"result_count": len(results), "query": query},
                render_hints={"icon": "code"},
            ))
            rows = [[r.get("name", ""), r.get("url", ""), r.get("language", ""),
                      str(r.get("stars", r.get("score", ""))), str(r.get("relevance", ""))]
                     for r in results[:50]]
            self._reporter.emit_output(AgentOutput(
                display_type="table",
                title=f"Similar Implementations ({len(results)})",
                data={"headers": ["Name", "URL", "Language", "Stars/Score", "Relevance"], "rows": rows},
            ))
            if guide:
                self._reporter.emit_output(AgentOutput(
                    display_type="markdown",
                    title="Implementation Guide",
                    content=guide,
                ))
        return None
