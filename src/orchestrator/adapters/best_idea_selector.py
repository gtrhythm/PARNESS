import logging
from typing import Any, Dict, List

from .base import BaseModule

logger = logging.getLogger(__name__)


class BestIdeaSelectorModule(BaseModule):
    module_name = "best_idea_selector"

    INPUT_SPEC = {
        "ranked_ideas": {"type": "list", "required": False, "default": []},
        "ideas": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "best_idea": {"type": "dict"},
        "idea_title": {"type": "str"},
        "idea_description": {"type": "str"},
        "selected_score": {"type": "float"},
        "all_ideas_count": {"type": "int"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        ideas = inputs.get("ranked_ideas", inputs.get("ideas", []))
        if not isinstance(ideas, list):
            ideas = []

        if not ideas:
            logger.warning("[BestIdeaSelector] No ideas provided")
            return {
                "best_idea": {},
                "idea_title": "",
                "idea_description": "",
                "selected_score": 0.0,
                "all_ideas_count": 0,
            }

        best = max(ideas, key=lambda x: self._get_score(x))

        title = best.get("title", "Untitled")
        description = best.get("description", "")
        score = self._get_score(best)

        logger.info(
            "[BestIdeaSelector] Selected '%s' with score %.2f from %d ideas",
            title[:60], score, len(ideas),
        )

        return {
            "best_idea": best,
            "idea_title": title,
            "idea_description": description,
            "selected_score": score,
            "all_ideas_count": len(ideas),
        }

    @staticmethod
    def _get_score(idea: Dict[str, Any]) -> float:
        score_keys = ["overall_score", "score", "avg_score"]
        for key in score_keys:
            val = idea.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
        novelty = idea.get("novelty_score", 0)
        feasibility = idea.get("feasibility_score", 0)
        impact = idea.get("impact_score", 0)
        try:
            return (float(novelty) + float(feasibility) + float(impact)) / 3
        except (TypeError, ValueError):
            return 0.0
