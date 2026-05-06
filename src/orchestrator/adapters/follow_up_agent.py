import logging
from typing import Any, Dict, Optional

from ..adapters.base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class FollowUpAgentModule(LLMAgentModule):
    module_name: str = "follow_up_agent"

    INPUT_SPEC = {
        "papers": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "follow_up_ideas": {"type": "list"},
        "follow_up_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.follow_up import FollowUpAgent

        llm_client = self._get_llm_client()

        papers = inputs.get("papers", [])
        if not papers:
            return {"follow_up_ideas": [], "follow_up_count": 0}

        max_concurrent = self.config.get("max_concurrent", 4)
        agent = FollowUpAgent(llm_client, max_concurrent=max_concurrent)
        follow_ups = await agent.analyze_all(papers)

        logger.info("FollowUpAgentModule: found %d follow-up ideas from %d papers",
                     len(follow_ups), len(papers))
        return {
            "follow_up_ideas": [f.to_dict() for f in follow_ups],
            "follow_up_count": len(follow_ups),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        follow_ups = result.get("follow_up_ideas", [])
        items = [{"label": f.get("title", "")[:80], "metadata": {
            "paper": f.get("paper_title", ""),
            "feasibility": f.get("feasibility", ""),
            "novelty": f.get("novelty", ""),
            "resources": f.get("resources", ""),
        }} for f in follow_ups]
        return AgentOutput(
            display_type="list",
            title="Follow-Up Research Directions",
            data={"items": items},
        )
