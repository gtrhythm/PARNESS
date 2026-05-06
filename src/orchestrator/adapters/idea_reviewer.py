import logging
from typing import Any, Dict, List

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class IdeaReviewerModule(LLMAgentModule):
    module_name = "idea_reviewer"

    INPUT_SPEC = {
        "ideas": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "reviewed_ideas": {"type": "list"},
        "review_report": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_reviewer.reviewer import IdeaReviewer
        from src.idea_reviewer.models import IdeaReviewInput

        llm_client = self._get_llm_client()

        ideas = inputs.get("ideas", [])
        if not ideas:
            return {
                "reviewed_ideas": [],
                "review_report": "No ideas to review",
            }

        reviewer = IdeaReviewer(llm_client)
        reviewed = []
        failed = 0

        for idea in ideas:
            try:
                review_input = IdeaReviewInput(
                    idea_title=idea.get("title", ""),
                    idea_description=idea.get("description", ""),
                    category=idea.get("category", ""),
                )
                review_output = await reviewer.review_idea(review_input)
                score = review_output.overall_score if hasattr(review_output, "overall_score") else 0
                idea_with_review = dict(idea)
                idea_with_review["review"] = {
                    "score": score,
                    "critiques": [
                        {
                            "aspect": c.aspect if hasattr(c, "aspect") else "",
                            "severity": c.severity if hasattr(c, "severity") else "",
                            "description": c.description if hasattr(c, "description") else "",
                            "suggestion": c.suggestion if hasattr(c, "suggestion") else "",
                        }
                        for c in (review_output.critiques if hasattr(review_output, "critiques") else [])
                    ],
                }
                reviewed.append(idea_with_review)
                if self.has_progress_reporter:
                    self._reporter.emit("idea_reviewed", score=score)
                    self._reporter.emit_output(AgentOutput(
                        display_type="table",
                        title=f"Idea Review (streaming)",
                        data={"reviews": [{"title": idea.get("title", "")[:80], "score": score,
                                           "novelty_score": idea.get("novelty_score", 0),
                                           "feasibility_score": idea.get("feasibility_score", 0),
                                           "impact_score": idea.get("impact_score", 0)}]},
                        render_hints={"streaming": True},
                    ))
            except Exception as e:
                logger.warning("Failed to review idea '%s': %s", idea.get("title", "?"), e)
                reviewed.append(idea)
                failed += 1

        report = f"Reviewed {len(reviewed)}/{len(ideas)} ideas"
        logger.info(report)

        return {
            "reviewed_ideas": reviewed,
            "review_report": report,
            "_failed": failed,
        }

    def emit_output(self, result):
        if result.get("error") or not result.get("reviewed_ideas"):
            return None
        reviewed = result.get("reviewed_ideas", [])
        failed = result.get("_failed", 0)
        reviews_data = []
        for idea in reviewed:
            review = idea.get("review", {})
            reviews_data.append({
                "title": idea.get("title", "")[:80],
                "score": review.get("score", 0),
                "novelty_score": idea.get("novelty_score", 0),
                "feasibility_score": idea.get("feasibility_score", 0),
                "impact_score": idea.get("impact_score", 0),
            })
        reviews_data.sort(key=lambda x: x["score"], reverse=True)
        avg_score = sum(r["score"] for r in reviews_data) / max(len(reviews_data), 1)
        return AgentOutput(
            display_type="table",
            title="Idea Reviews (aggregate)",
            data={"reviews": reviews_data, "total_reviewed": len(reviewed) - failed,
                  "total_failed": failed, "avg_score": avg_score},
            render_hints={"sort_by": "score", "sort_desc": True, "score_color_range": {"low": 4.0, "high": 9.0}},
        )
