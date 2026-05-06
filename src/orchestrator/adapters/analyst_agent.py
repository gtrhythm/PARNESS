import logging
from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class AnalystAgentModule(LLMAgentModule):
    module_name = "analyst_agent"

    INPUT_SPEC = {
        "compressed_insights": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "analyst_seeds": {"type": "list"},
        "clusters": {"type": "list"},
        "knowledge_base": {"type": "dict"},
        "cross_cluster_gaps": {"type": "list"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.analyst import AnalystAgent
        from src.idea_agents.models import CompressedInsight
        from src.idea_agents.token_budget import PromptBudget

        insights_data = inputs.get("compressed_insights", [])

        llm_client = self._get_llm_client()

        if not insights_data:
            return {"analyst_seeds": [], "clusters": [], "knowledge_base": {}, "cross_cluster_gaps": []}

        insights = [CompressedInsight.from_dict(d) for d in insights_data]
        budget = PromptBudget.from_config(self.config)
        agent = AnalystAgent(llm_client, budget=budget)
        agent_result = await agent.analyze(insights)

        return {
            "analyst_seeds": [s.to_dict() for s in agent_result["seeds"]],
            "clusters": [c.to_dict() for c in agent_result["clusters"]],
            "knowledge_base": {
                "analyst_seeds": [s.to_dict() for s in agent_result["seeds"]],
                "clusters": [c.to_dict() for c in agent_result["clusters"]],
            },
            "cross_cluster_gaps": agent_result.get("cross_cluster_gaps", []),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        clusters = result.get("clusters", [])
        if not clusters:
            return None
        cluster_data = []
        for cd in clusters:
            cluster_data.append({
                "theme": cd.get("theme", ""),
                "insight_count": cd.get("insight_count", 0),
                "limitations": cd.get("limitations", ""),
                "gap_count": cd.get("gap_count", 0),
                "seed_type": cd.get("seed_type", ""),
            })
        cross_cluster_gaps = result.get("cross_cluster_gaps", [])
        return AgentOutput(
            display_type="table",
            title="Insight Clusters & Research Gaps",
            data={"clusters": cluster_data, "cross_cluster_gaps": cross_cluster_gaps,
                  "total_clusters": len(clusters), "total_seeds": len(result.get("analyst_seeds", []))},
            render_hints={"sort_by": "gap_count", "sort_desc": True},
        )
