import logging
from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class ContrarianAgentModule(LLMAgentModule):
    module_name = "contrarian_agent"

    INPUT_SPEC = {
        "compressed_insights": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "contrarian_seeds": {"type": "list"},
        "knowledge_base": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.contrarian import ContrarianAgent
        from src.idea_agents.models import CompressedInsight
        from src.idea_agents.token_budget import PromptBudget

        insights_data = inputs.get("compressed_insights", [])

        llm_client = self._get_llm_client()

        if not insights_data:
            return {"contrarian_seeds": [], "knowledge_base": {}}

        insights = [CompressedInsight.from_dict(d) for d in insights_data]
        budget = PromptBudget.from_config(self.config)
        agent = ContrarianAgent(llm_client, budget=budget)
        agent_result = await agent.challenge(insights)

        return {
            "contrarian_seeds": [s.to_dict() for s in agent_result["seeds"]],
            "knowledge_base": {
                "contrarian_seeds": [s.to_dict() for s in agent_result["seeds"]],
            },
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        seeds = result.get("contrarian_seeds", [])
        if not seeds:
            return None
        seeds_data = []
        for sd in seeds:
            seeds_data.append({
                "seed": sd.get("seed", ""),
                "challenged_assumption": sd.get("challenged_assumption", ""),
                "flipped_to": sd.get("flipped_to", ""),
                "rationale": sd.get("rationale", ""),
                "source_papers": sd.get("source_papers", []),
            })
        return AgentOutput(
            display_type="table",
            title="Contrarian Idea Seeds",
            data={"seeds": seeds_data},
            render_hints={"highlight_column": "flipped_to"},
        )
