import logging
from typing import Any, Dict, Optional

from ..adapters.base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class IdeaRefinerModule(LLMAgentModule):
    module_name: str = "idea_refiner"

    INPUT_SPEC = {
        "ideas": {"type": "list", "required": False, "default": []},
        "explorations": {"type": "list", "required": False, "default": []},
        "direction": {"type": "dict", "required": False, "default": None},
    }
    OUTPUT_SPEC = {
        "refined_ideas": {"type": "list"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.refiner import RefinerAgent
        from src.idea_agents.models import FullIdea, IdeaExplorationResult, ResearchDirection

        llm_client = self._get_llm_client()

        ideas_data = inputs.get("ideas", [])
        ideas = [FullIdea.from_dict(d) for d in ideas_data]
        explorations_data = inputs.get("explorations", [])
        explorations = [IdeaExplorationResult.from_dict(d) for d in explorations_data]
        direction_data = inputs.get("direction")
        direction = ResearchDirection.from_dict(direction_data) if direction_data else None
        agent = RefinerAgent(llm_client)
        results = await agent.refine_batch(ideas, explorations, direction)

        return {"refined_ideas": [i.to_dict() for i in results]}

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        refined = result.get("refined_ideas", [])
        ideas_data = [{
            "original_title": i.get("original_title", "")[:80],
            "refined_title": i.get("refined_title", i.get("title", ""))[:80],
            "category": i.get("category", ""),
            "rationale_snippet": i.get("rationale", "")[:80],
        } for i in refined]
        return AgentOutput(
            display_type="table",
            title="Idea Refinement",
            data={"refined_count": len(refined), "total_input": len(ideas_data), "ideas": ideas_data},
            render_hints={"max_rows": 20, "truncate": 80},
        )
