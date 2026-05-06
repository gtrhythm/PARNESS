import json
import logging
from typing import Any, Dict

from .base import LLMAgentModule

logger = logging.getLogger(__name__)


class IdeaEvolutionAgentModule(LLMAgentModule):
    module_name = "idea_evolution_agent"

    INPUT_SPEC = {
        "merged_summaries": {"type": "str", "required": False, "default": ""},
        "previous_ideas": {"type": "list", "required": False, "default": []},
        "resource_constraint": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "ideas": {"type": "list"},
        "round_report": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        merged_summaries = inputs.get("merged_summaries", "")
        previous_ideas = inputs.get("previous_ideas", [])
        resource_constraint = inputs.get(
            "resource_constraint",
            self.config.get(
                "resource_constraint",
                "feasible on a single NVIDIA V100 32GB GPU",
            ),
        )
        ideas_per_round = self.config.get("ideas_per_round", 3)

        if not merged_summaries:
            return {"ideas": [], "round_report": "No summaries provided"}

        max_summary = self.config.get("max_summary_chars", 25000)
        if len(merged_summaries) > max_summary:
            merged_summaries = merged_summaries[:max_summary]

        llm_client = self._get_llm_client()

        prev_section = ""
        if previous_ideas:
            prev_items = []
            for i, idea in enumerate(previous_ideas, 1):
                if isinstance(idea, dict):
                    desc = idea.get("description", "")[:150]
                    title = idea.get("title", "Untitled")[:80]
                    prev_items.append(f"{i}. {title}: {desc}")
                else:
                    prev_items.append(f"{i}. {str(idea)[:150]}")
            prev_text = "\n".join(prev_items)
            if len(prev_text) > 3000:
                prev_text = prev_text[:3000]
            prev_section = (
                "\n\nPrevious round's research ideas (build upon or diverge from these):\n"
                + prev_text
            )

        prompt = (
            "You are an expert research ideation strategist. Based on the following "
            "analysis of research papers, generate exactly "
            f"{ideas_per_round} novel research ideas.\n\n"
            f"Paper Analysis:\n{merged_summaries}\n"
            f"{prev_section}\n\n"
            "HARD CONSTRAINT: Every idea must be implementable on a single NVIDIA V100 32GB GPU. "
            "This means:\n"
            "- Model size must fit in 32GB VRAM (e.g., models up to ~7B parameters with mixed precision)\n"
            "- Training/inference must complete within reasonable time on 1 GPU\n"
            "- Datasets should be publicly available and manageable in size\n\n"
            "For each idea, provide:\n"
            "1. A concise, specific title\n"
            "2. A description (150-300 words): motivation, proposed method, novelty, contribution\n"
            "3. Self-assessed scores (0-10) for: novelty, feasibility, impact\n"
            "4. A brief methodology outline\n"
            "5. Expected results and how to measure them\n\n"
            "Guidelines:\n"
            "- Ideas should be concrete and actionable\n"
            "- Each idea should explore a DIFFERENT angle\n"
            "- If previous ideas are provided, EVOLVE from them\n"
            "- Prioritize novelty and practical feasibility\n\n"
            "Return a JSON object with:\n"
            "- \"ideas\": array of objects with: title, description, novelty_score, feasibility_score, "
            "impact_score, methodology, expected_results\n"
            "- \"round_report\": a brief paragraph summarizing the ideation direction\n\n"
            "Return ONLY the JSON object, no other text."
        )

        if len(prompt) > 30000:
            prompt = prompt[:30000]

        response = await llm_client.chat(prompt)
        raw = response if isinstance(response, str) else str(response)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(raw[start:end])
                except json.JSONDecodeError:
                    parsed = {}
            else:
                parsed = {}

        ideas = parsed.get("ideas", [])
        if not isinstance(ideas, list):
            ideas = []

        for i, idea in enumerate(ideas):
            if not isinstance(idea, dict):
                ideas[i] = {"title": str(idea), "description": str(idea)}
            else:
                desc = idea.get("description", "")
                if len(desc) > 2000:
                    idea["description"] = desc[:2000]

        round_report = parsed.get("round_report", "")
        if len(round_report) > 1000:
            round_report = round_report[:1000]

        logger.info(
            "[IdeaEvolutionAgent] Generated %d ideas, report: %s",
            len(ideas),
            round_report[:100],
        )

        return {
            "ideas": ideas,
            "round_report": round_report,
        }
