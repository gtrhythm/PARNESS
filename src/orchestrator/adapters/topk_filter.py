import logging
from typing import Any, Dict, List, Optional

from .base import BaseModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class TopKFilterModule(BaseModule):
    module_name = "topk_filter"

    INPUT_SPEC = {
        "ranked_ideas": {"type": "list", "required": False, "default": []},
        "target_count": {"type": "int", "required": False, "default": 20},
        "min_score": {"type": "float", "required": False, "default": 6.0},
    }
    OUTPUT_SPEC = {
        "selected_ideas": {"type": "list"},
        "rejected_count": {"type": "int"},
        "total_input": {"type": "int"},
        "_min_score": {"type": "float"},
        "_target_count": {"type": "int"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        ranked_ideas = inputs.get("ranked_ideas", [])
        target_count = inputs.get("target_count", self.config.get("target_count", 20))
        min_score = inputs.get("min_score", self.config.get("min_score", 6.0))

        filtered = [
            idea for idea in ranked_ideas
            if idea.get("overall_score", 0) >= min_score
        ]

        selected = filtered[:target_count]
        rejected_count = len(ranked_ideas) - len(selected)

        logger.info(
            "TopK filter: %d -> %d (min_score=%.1f, target=%d)",
            len(ranked_ideas), len(selected), min_score, target_count,
        )

        if len(selected) < target_count:
            logger.warning(
                "Only %d ideas meet criteria (target=%d, min_score=%.1f). "
                "Consider lowering min_score.",
                len(selected), target_count, min_score,
            )

        return {
            "selected_ideas": selected,
            "rejected_count": rejected_count,
            "total_input": len(ranked_ideas),
            "_min_score": min_score,
            "_target_count": target_count,
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        selected = result.get("selected_ideas", [])
        rejected_count = result.get("rejected_count", 0)
        total_input = result.get("total_input", 0)
        min_score = result.get("_min_score", 6.0)
        target_count = result.get("_target_count", 20)
        selected_ideas_data = [{
            "title": i.get("title", "")[:80],
            "overall_score": i.get("overall_score", 0),
            "category": i.get("category", ""),
        } for i in selected]
        return AgentOutput(
            display_type="chart",
            title="Top-K Filter",
            content=f"Selected {len(selected)} ideas from {total_input} (min_score={min_score})",
            data={"selected_count": len(selected), "rejected_count": rejected_count,
                  "total_input": total_input, "min_score": min_score,
                  "target_count": target_count, "selected_ideas": selected_ideas_data},
            render_hints={"chart_type": "bar", "x_field": "overall_score", "threshold_line": min_score,
                          "color_by": "category"},
        )
