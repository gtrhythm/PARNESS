import logging
from typing import Any, Dict, Optional

from ..adapters.base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class MetaAnalysisAgentModule(LLMAgentModule):
    module_name: str = "meta_analysis_agent"

    INPUT_SPEC = {
        "compressed_insights": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "trends": {"type": "list"},
        "meta_gaps": {"type": "list"},
        "trend_count": {"type": "int"},
        "gap_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.meta_analysis import MetaAnalysisAgent
        from src.idea_agents.models import CompressedInsight

        llm_client = self._get_llm_client()

        insights_data = inputs.get("compressed_insights", [])
        if not insights_data:
            return {"trends": [], "meta_gaps": [], "trend_count": 0, "gap_count": 0}

        insights = [CompressedInsight.from_dict(d) for d in insights_data]
        agent = MetaAnalysisAgent(llm_client)
        result = await agent.analyze(insights)

        return {
            "trends": [t.to_dict() for t in result["trends"]],
            "meta_gaps": [g.to_dict() for g in result["gaps"]],
            "trend_count": len(result["trends"]),
            "gap_count": len(result["gaps"]),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        if not self.has_progress_reporter:
            return None
        trends = result.get("trends", [])
        gaps = result.get("meta_gaps", [])
        rows = [[t.get("trend", "")[:60], t.get("description", "")[:80],
                  str(t.get("growth", "")), t.get("supporting_papers", "")]
                 for t in trends[:50]]
        self._reporter.emit_output(AgentOutput(
            display_type="table",
            title="Research Trends",
            data={"headers": ["Trend", "Description", "Growth", "Supporting Papers"], "rows": rows},
        ))
        gap_items = [{"label": g.get("gap", ""), "metadata": {
            "domain": g.get("domain", ""),
            "opportunity_score": g.get("opportunity_score", 0),
            "evidence_papers": g.get("evidence_papers", []),
        }} for g in gaps]
        self._reporter.emit_output(AgentOutput(
            display_type="list",
            title="Identified Gaps",
            data={"items": gap_items},
            render_hints={"show_scores": True, "score_key": "opportunity_score"},
        ))
        return None
