from typing import Any, Dict, List
from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput


class IdeaEvaluatorModule(LLMAgentModule):
    module_name = "idea_evaluator"

    INPUT_SPEC = {
        "ideas": {"type": "list", "required": False, "default": []},
        "available_datasets": {"type": "list", "required": False, "default": []},
        "available_compute": {"type": "str", "required": False, "default": "medium"},
    }
    OUTPUT_SPEC = {
        "evaluations": {"type": "list"},
        "ranked_ideas": {"type": "list"},
        "summary": {"type": "str"},
        "count": {"type": "int"},
        "avg_score": {"type": "float"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_evaluator.evaluator import IdeaEvaluator
        from src.idea_evaluator.models import IdeaEvaluatorInput
        from src.idea_generator.models import Idea, IdeaCategory

        ideas_data = inputs.get("ideas", [])

        llm_client = self._get_llm_client()

        evaluator = IdeaEvaluator(llm_client=llm_client)

        available_datasets = inputs.get("available_datasets", [])
        available_compute = inputs.get("available_compute", "medium")

        ideas = self._convert_ideas(ideas_data)

        eval_input = IdeaEvaluatorInput(
            ideas=ideas,
            available_datasets=available_datasets,
            available_compute=available_compute,
        )

        output = await evaluator.evaluate(eval_input)

        evaluations = [
            {
                "idea_title": e.idea.title if e.idea else "",
                "novelty_score": e.novelty_score,
                "feasibility_score": e.feasibility_score,
                "impact_score": e.impact_score,
                "overall_score": e.overall_score,
                "strengths": e.strengths,
                "weaknesses": e.weaknesses,
                "recommendations": e.recommendations,
            }
            for e in output.evaluations
        ]

        ranked_ideas = [
            {
                "id": idea.id,
                "title": idea.title,
                "description": idea.description,
                "category": idea.category.value if hasattr(idea.category, "value") else str(idea.category),
                "novelty_score": idea.novelty_score,
                "feasibility_score": idea.feasibility_score,
                "impact_score": idea.impact_score,
                "overall_score": idea.overall_score(),
                "methodology": getattr(idea, "methodology", ""),
                "expected_results": getattr(idea, "expected_results", ""),
                "required_resources": getattr(idea, "required_resources", ""),
                "risk_analysis": getattr(idea, "risk_analysis", ""),
            }
            for idea in output.ranked_ideas
        ]

        avg_score = sum(e.overall_score for e in output.evaluations) / len(output.evaluations) if output.evaluations else 0.0

        return {
            "evaluations": evaluations,
            "ranked_ideas": ranked_ideas,
            "summary": output.summary,
            "count": len(evaluations),
            "avg_score": avg_score,
        }

    def emit_output(self, result):
        evaluations = result.get("evaluations", [])
        avg_score = result.get("avg_score", 0.0)
        metrics_data = {
            "evaluated_count": result["count"],
            "avg_score": avg_score,
            "avg_novelty": sum(e.get("novelty_score", 0) for e in evaluations) / max(len(evaluations), 1),
            "avg_feasibility": sum(e.get("feasibility_score", 0) for e in evaluations) / max(len(evaluations), 1),
            "avg_impact": sum(e.get("impact_score", 0) for e in evaluations) / max(len(evaluations), 1),
        }
        return AgentOutput(
            display_type="metrics",
            title="Idea Quality Evaluation",
            content=f"Evaluated {result['count']} ideas, avg score: {avg_score:.2f}",
            data={"metrics": metrics_data, "evaluations": evaluations},
            render_hints={"show_radar_chart": True, "sort_by": "overall_score", "sort_desc": True},
        )

    def _convert_ideas(self, ideas_data):
        from src.idea_generator.models import Idea, IdeaCategory

        ideas = []
        for item in ideas_data:
            if isinstance(item, Idea):
                ideas.append(item)
            elif isinstance(item, dict):
                category_str = item.get("category", "combination")
                try:
                    if isinstance(category_str, str):
                        category = IdeaCategory(category_str.lower())
                    else:
                        category = IdeaCategory.COMBINATION
                except (ValueError, KeyError):
                    category = IdeaCategory.COMBINATION

                ideas.append(Idea(
                    id=item.get("id", ""),
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    category=category,
                    novelty_score=item.get("novelty_score", 0.0),
                    feasibility_score=item.get("feasibility_score", 0.0),
                    impact_score=item.get("impact_score", 0.0),
                    methodology=item.get("methodology", ""),
                    expected_results=item.get("expected_results", ""),
                    required_resources=item.get("required_resources", ""),
                    risk_analysis=item.get("risk_analysis", ""),
                ))
        return ideas
