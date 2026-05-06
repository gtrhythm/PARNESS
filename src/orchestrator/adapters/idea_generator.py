from typing import Any, Dict
from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput


class IdeaGeneratorModule(LLMAgentModule):
    module_name = "idea_generator"

    INPUT_SPEC = {
        "target_count": {"type": "int", "required": False, "default": 20},
        "generation_strategy": {"type": "str", "required": False, "default": "diverse"},
        "innovations": {"type": "list", "required": False, "default": []},
        "references": {"type": "list", "required": False, "default": []},
        "task_domain": {"type": "str", "required": False, "default": ""},
        "existing_ideas": {"type": "list", "required": False, "default": []},
        "focus_areas": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "ideas": {"type": "list"},
        "report": {"type": "str"},
        "count": {"type": "int"},
        "avg_score": {"type": "float"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_generator.generator import IdeaGenerator
        from src.idea_generator.models import IdeaGeneratorInput

        target_count = inputs.get("target_count", self.config.get("target_count", 20))
        strategy = inputs.get("generation_strategy", self.config.get("generation_strategy", "diverse"))

        llm_client = self._get_llm_client()

        gen = IdeaGenerator(llm_client=llm_client)

        innovations = inputs.get("innovations", [])
        references = inputs.get("references", [])
        task_domain = inputs.get("task_domain", "")
        existing_ideas = inputs.get("existing_ideas", [])
        focus_areas = inputs.get("focus_areas", self.config.get("focus_areas", []))

        gen_input = IdeaGeneratorInput(
            innovations=innovations,
            references=references,
            task_domain=task_domain,
            target_count=target_count,
            existing_ideas=existing_ideas,
            focus_areas=focus_areas,
            generation_strategy=strategy,
        )

        output = await gen.generate(gen_input)
        return {
            "ideas": [
                {
                    "id": idea.id,
                    "title": idea.title,
                    "description": idea.description,
                    "category": idea.category.value if hasattr(idea.category, "value") else str(idea.category),
                    "novelty_score": idea.novelty_score,
                    "feasibility_score": idea.feasibility_score,
                    "impact_score": idea.impact_score,
                    "overall_score": idea.overall_score(),
                    "methodology": idea.methodology,
                    "expected_results": idea.expected_results,
                    "required_resources": idea.required_resources,
                    "risk_analysis": idea.risk_analysis,
                    "related_work_diff": idea.related_work_diff,
                    "source_paper_ids": idea.source_paper_ids,
                }
                for idea in output.ideas
            ],
            "report": output.generation_report,
            "count": len(output.ideas),
            "avg_score": sum(i.overall_score() for i in output.ideas) / len(output.ideas) if output.ideas else 0.0,
            "_target_count": target_count,
            "_strategy": strategy,
        }

    def emit_output(self, result):
        ideas = result.get("ideas", [])
        target_count = result.get("_target_count", self.config.get("target_count", 20))
        strategy = result.get("_strategy", self.config.get("generation_strategy", "diverse"))
        categories = {}
        for idea in ideas:
            cat = idea.get("category", "")
            categories[cat] = categories.get(cat, 0) + 1
        top_ideas = [{"title": i.get("title", "")[:80], "category": i.get("category", ""),
                      "overall_score": i.get("overall_score", 0)} for i in ideas[:10]]
        return AgentOutput(
            display_type="metrics",
            title="Idea Generation Summary",
            content=f"Generated {result['count']} ideas with avg score {result['avg_score']:.2f}",
            data={"metrics": {"ideas_count": result["count"], "target_count": target_count,
                              "avg_score": result["avg_score"], "strategy": strategy, "categories": categories},
                  "top_ideas": top_ideas},
            render_hints={"show_category_distribution": True, "chart_type": "bar"},
        )
