import logging
from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class DirectionFilterModule(LLMAgentModule):
    module_name = "direction_filter"

    INPUT_SPEC = {
        "papers": {"type": "list", "required": False, "default": []},
        "direction": {"type": "dict", "required": False, "default": None},
        "max_papers": {"type": "int", "required": False, "default": 50},
        "relevance_threshold": {"type": "float", "required": False, "default": 0.5},
    }
    OUTPUT_SPEC = {
        "filtered_papers": {"type": "list"},
        "relevance_scores": {"type": "list"},
        "filter_stats": {"type": "dict"},
        "_relevance_threshold": {"type": "float"},
        "_kept_count": {"type": "int"},
        "_filtered_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.direction_filter import DirectionFilter
        from src.idea_agents.models import ResearchDirection

        llm_client = self._get_llm_client()

        papers = inputs.get("papers", [])
        if not papers:
            return {"filtered_papers": [], "relevance_scores": [], "filter_stats": {"input_count": 0}, "_relevance_threshold": 0.0, "_kept_count": 0, "_filtered_count": 0}

        direction_data = inputs.get("direction")
        direction = ResearchDirection.from_dict(direction_data) if direction_data else ResearchDirection()
        max_papers = inputs.get("max_papers", self.config.get("max_papers", 50))
        relevance_threshold = inputs.get("relevance_threshold", self.config.get("relevance_threshold", 0.5))

        agent = DirectionFilter(llm_client)
        result = await agent.filter(papers, direction, max_papers=max_papers, relevance_threshold=relevance_threshold)

        logger.info("DirectionFilter: %d -> %d papers (threshold=%.2f, avg_relevance=%.2f)",
                     result.filter_stats.get("input_count", 0),
                     len(result.filtered_papers),
                     relevance_threshold,
                     result.filter_stats.get("avg_relevance", 0.0))

        kept_count = len(result.filtered_papers)
        filtered_count = result.filter_stats.get("input_count", len(papers)) - kept_count
        return {
            "filtered_papers": result.filtered_papers,
            "relevance_scores": result.relevance_scores,
            "filter_stats": result.filter_stats,
            "_relevance_threshold": relevance_threshold,
            "_kept_count": kept_count,
            "_filtered_count": filtered_count,
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        if not result.get("filtered_papers"):
            return None
        filtered_papers = result["filtered_papers"]
        relevance_scores = result.get("relevance_scores", [])
        filter_stats = result.get("filter_stats", {})
        kept_count = result.get("_kept_count", 0)
        filtered_count = result.get("_filtered_count", 0)
        relevance_threshold = result.get("_relevance_threshold", 0.5)
        top_papers_data = [{
            "title": p.get("title", "")[:80],
            "relevance": relevance_scores[i] if i < len(relevance_scores) else 0,
        } for i, p in enumerate(filtered_papers[:10])]
        return AgentOutput(
            display_type="chart",
            title="Direction Filter",
            content=f"Kept {kept_count} papers, filtered {filtered_count} (threshold={relevance_threshold})",
            data={"input_count": filter_stats.get("input_count", 0),
                  "kept_count": kept_count, "filtered_count": filtered_count,
                  "avg_relevance": filter_stats.get("avg_relevance", 0),
                  "filter_stats": filter_stats, "top_papers": top_papers_data},
            render_hints={"chart_type": "histogram", "x_field": "relevance", "threshold_line": relevance_threshold},
        )
