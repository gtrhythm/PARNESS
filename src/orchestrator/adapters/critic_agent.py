import logging
from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class CriticAgentModule(LLMAgentModule):
    module_name = "critic_agent"

    INPUT_SPEC = {
        "full_ideas": {"type": "list", "required": False, "default": []},
        "compressed_insights": {"type": "list", "required": False, "default": []},
        "existing_ideas": {"type": "list", "required": False, "default": []},
        "target_count": {"type": "int", "required": False, "default": 20},
    }
    OUTPUT_SPEC = {
        "ranked_ideas": {"type": "list"},
        "final_count": {"type": "int"},
        "total_accumulated": {"type": "int"},
        "avg_score": {"type": "float"},
        "_total_input": {"type": "int"},
        "_avg_novelty": {"type": "float"},
        "_avg_feasibility": {"type": "float"},
        "_avg_impact": {"type": "float"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.critic import CriticAgent
        from src.idea_agents.models import FullIdea, CompressedInsight
        from src.idea_agents.token_budget import PromptBudget

        llm_client = self._get_llm_client()

        ideas_data = inputs.get("full_ideas", [])
        ideas = [FullIdea.from_dict(d) for d in ideas_data]

        insights_data = inputs.get("compressed_insights", [])
        insights = [CompressedInsight.from_dict(d) for d in insights_data]

        existing_ideas = inputs.get("existing_ideas", [])
        existing_titles = {i.get("title", "").lower().strip() for i in existing_ideas if i.get("title")}

        if not ideas:
            return {
                "ranked_ideas": existing_ideas,
                "final_count": len(existing_ideas),
                "total_accumulated": len(existing_ideas),
                "avg_score": 0.0,
                "_total_input": 0,
                "_avg_novelty": 0.0,
                "_avg_feasibility": 0.0,
                "_avg_impact": 0.0,
            }

        target_count = inputs.get("target_count", self.config.get("target_count", 20))
        budget = PromptBudget.from_config(self.config)
        agent = CriticAgent(llm_client, budget=budget)
        ranked = await agent.critique(ideas, insights, target_count=target_count)

        new_ranked = []
        for idea in ranked:
            if idea.title.lower().strip() not in existing_titles:
                new_ranked.append(idea)
                existing_titles.add(idea.title.lower().strip())

        logger.info("Critic: %d new unique + %d existing = %d total",
                     len(new_ranked), len(existing_ideas),
                     len(existing_ideas) + len(new_ranked))

        return {
            "ranked_ideas": [i.to_dict() for i in new_ranked],
            "final_count": len(new_ranked),
            "total_accumulated": len(existing_ideas) + len(new_ranked),
            "avg_score": sum(i.overall_score for i in new_ranked) / max(len(new_ranked), 1),
            "_total_input": len(ideas_data),
            "_avg_novelty": sum(i.novelty_score for i in new_ranked) / max(len(new_ranked), 1),
            "_avg_feasibility": sum(i.feasibility_score for i in new_ranked) / max(len(new_ranked), 1),
            "_avg_impact": sum(i.impact_score for i in new_ranked) / max(len(new_ranked), 1),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        if "_total_input" not in result:
            return None
        ranked = result.get("ranked_ideas", [])
        metrics_data = {
            "total_input": result["_total_input"],
            "ranked_count": result["final_count"],
            "avg_score": result["avg_score"],
            "avg_novelty": result["_avg_novelty"],
            "avg_feasibility": result["_avg_feasibility"],
            "avg_impact": result["_avg_impact"],
        }
        ranked_ideas_data = [{
            "title": i.get("title", "")[:80],
            "overall_score": i.get("overall_score", 0),
            "novelty_score": i.get("novelty_score", 0),
            "feasibility_score": i.get("feasibility_score", 0),
            "impact_score": i.get("impact_score", 0),
            "recommendation": "accept" if i.get("overall_score", 0) >= 7.0 else "review",
        } for i in ranked]
        return AgentOutput(
            display_type="metrics",
            title="Critic Evaluation Results",
            content=f"Evaluated {result['final_count']} ideas, avg score: {result['avg_score']:.2f}",
            data={"metrics": metrics_data, "ranked_ideas": ranked_ideas_data},
            render_hints={"score_color_range": {"low": 5.0, "high": 9.0}, "show_radar_chart": True},
        )
