import logging
from typing import Any, Dict, Optional

from ..adapters.base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class IdeaScoutModule(LLMAgentModule):
    module_name: str = "idea_scout"

    INPUT_SPEC = {
        "ideas": {"type": "list", "required": False, "default": []},
        "direction": {"type": "dict", "required": False, "default": None},
    }
    OUTPUT_SPEC = {
        "explorations": {"type": "list"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.scout import ScoutAgent
        from src.idea_agents.models import FullIdea, ExplorationConfig, ResearchDirection

        llm_client = self._get_llm_client()

        ideas_data = inputs.get("ideas", [])
        ideas = [FullIdea.from_dict(d) for d in ideas_data]
        direction_data = inputs.get("direction")
        direction = ResearchDirection.from_dict(direction_data) if direction_data else None
        max_papers_per_idea = self.config.get("max_papers_per_idea", 10)
        concurrency_per_idea = self.config.get("concurrency_per_idea", 4)
        config = ExplorationConfig(
            max_papers_per_idea=max_papers_per_idea,
            concurrency_per_idea=concurrency_per_idea,
        )
        agent = ScoutAgent(llm_client)
        results = await agent.explore_batch(ideas, config, direction)

        return {"explorations": [e.to_dict() for e in results]}

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        explorations = result.get("explorations", [])
        explorations_data = [{
            "idea_title": e.get("idea_title", ""),
            "search_queries": e.get("search_queries", []),
            "found_papers_count": e.get("found_papers_count", 0),
            "novelty_validation": e.get("novelty_validation", ""),
            "innovation_gaps": e.get("innovation_gaps", []),
        } for e in explorations]
        md_lines = ["# Idea Exploration & Novelty Validation\n"]
        for e in explorations[:10]:
            md_lines.append(f"\n## {e.get('idea_title', 'Untitled')}\n")
            md_lines.append(f"**Found Papers**: {e.get('found_papers_count', 0)}\n")
            if e.get("novelty_validation"):
                md_lines.append(f"**Novelty Validation**: {e['novelty_validation']}\n")
            if e.get("innovation_gaps"):
                md_lines.append(f"**Innovation Gaps**: {', '.join(e['innovation_gaps'][:3])}\n")
        return AgentOutput(
            display_type="markdown",
            title="Idea Exploration & Novelty Validation",
            content="".join(md_lines),
            data={"explorations": explorations_data},
            render_hints={"format": "exploration_cards", "collapse_papers": True, "max_display": 10},
        )
