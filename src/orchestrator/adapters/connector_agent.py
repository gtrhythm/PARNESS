import logging
from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class ConnectorAgentModule(LLMAgentModule):
    module_name = "connector_agent"

    INPUT_SPEC = {
        "compressed_insights": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "connector_seeds": {"type": "list"},
        "cross_domain_pairs": {"type": "list"},
        "knowledge_base": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.connector import ConnectorAgent
        from src.idea_agents.models import CompressedInsight
        from src.idea_agents.token_budget import PromptBudget

        insights_data = inputs.get("compressed_insights", [])
        max_pairs = self.config.get("max_pairs", 10)

        llm_client = self._get_llm_client()

        if not insights_data:
            return {"connector_seeds": [], "cross_domain_pairs": [], "knowledge_base": {}}

        insights = [CompressedInsight.from_dict(d) for d in insights_data]
        budget = PromptBudget.from_config(self.config)
        agent = ConnectorAgent(llm_client, max_pairs=max_pairs, budget=budget)
        agent_result = await agent.connect(insights)

        return {
            "connector_seeds": [s.to_dict() for s in agent_result["seeds"]],
            "cross_domain_pairs": [p.to_dict() for p in agent_result["pairs"]],
            "knowledge_base": {
                "connector_seeds": [s.to_dict() for s in agent_result["seeds"]],
                "cross_domain_pairs": [p.to_dict() for p in agent_result["pairs"]],
            },
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        pairs = result.get("cross_domain_pairs", [])
        if not pairs:
            return None
        connections = []
        for pd in pairs:
            connections.append({
                "structural_analogy": pd.get("structural_analogy", ""),
                "transfer_direction": pd.get("transfer_direction", ""),
                "surface_similarity": pd.get("surface_similarity", 0),
                "seed": pd.get("seed", ""),
                "rationale": pd.get("rationale", ""),
            })
        return AgentOutput(
            display_type="table",
            title="Cross-Domain Connections",
            data={"connections": connections},
            render_hints={"sort_by": "surface_similarity", "max_col_width": 80},
        )
