from typing import Any, Dict
from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput


class PaperReviewerModule(LLMAgentModule):
    module_name = "paper_reviewer"

    INPUT_SPEC = {
        "paper_content": {"type": "dict", "required": False, "default": {}},
        "paper_id": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "overall_score": {"type": "float"},
        "summary": {"type": "str"},
        "critiques": {"type": "list"},
        "confidence": {"type": "float"},
        "paper_id": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.paper_reviewer.reviewer import PaperReviewer
        from src.paper_reviewer.models import PaperReviewInput

        llm_client = self._get_llm_client()

        reviewer = PaperReviewer(llm_client=llm_client)

        paper_content = inputs.get("paper_content", {})
        paper_id = inputs.get("paper_id", "")

        review_input = PaperReviewInput(
            paper_content=paper_content,
            paper_id=paper_id,
        )

        output = await reviewer.review(review_input)
        return {
            "overall_score": output.overall_score,
            "summary": output.summary,
            "critiques": [
                {
                    "aspect": c.category if hasattr(c, "category") else "",
                    "score": c.severity if hasattr(c, "severity") else 0,
                    "comment": c.description if hasattr(c, "description") else "",
                }
                for c in output.critiques
            ],
            "confidence": output.confidence,
            "paper_id": output.paper_id,
        }

    def emit_output(self, result):
        critique_counts = {"critical": 0, "major": 0, "minor": 0, "suggestion": 0}
        for c in result.get("critiques", []):
            aspect_lower = c.get("aspect", "").lower()
            if "critical" in aspect_lower:
                critique_counts["critical"] += 1
            elif "major" in aspect_lower:
                critique_counts["major"] += 1
            elif "minor" in aspect_lower:
                critique_counts["minor"] += 1
            else:
                critique_counts["suggestion"] += 1
        return AgentOutput(
            display_type="metrics",
            title=f"Paper Review: Score {result.get('overall_score', 0):.1f}/10",
            content=result.get("summary", ""),
            data={"paper_id": result.get("paper_id", ""), "overall_score": result.get("overall_score", 0),
                  "confidence": result.get("confidence", 0), "critiques": result.get("critiques", []),
                  "critique_counts": critique_counts},
            render_hints={"score_bar": True, "max_score": 10, "threshold": 6.5,
                          "severity_colors": {"critical": "red", "major": "orange", "minor": "yellow", "suggestion": "blue"}},
        )
