import json
import logging
from typing import Any, Dict

from .base import LLMAgentModule

logger = logging.getLogger(__name__)


class PaperOutlineGeneratorModule(LLMAgentModule):
    module_name = "paper_outline_generator"

    INPUT_SPEC = {
        "idea": {"type": "str", "required": False, "default": ""},
        "experiment_report": {"type": "str", "required": False, "default": ""},
        "references": {"type": "list", "required": False, "default": []},
        "session_id": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "outline": {"type": "list"},
        "persistence_info": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.experiment_agents.persistence import PersistenceHelper

        idea = inputs.get("idea", "")
        experiment_report = inputs.get("experiment_report", "")
        references = inputs.get("references") or []

        llm_client = self._get_llm_client()

        prompt = self._build_prompt(idea, experiment_report, references)
        raw = await llm_client.chat(prompt)
        outline = self._parse_outline(raw)

        session_id = inputs.get("session_id", "")
        output_dir = PersistenceHelper.make_output_dir(
            "paper_outline", "outline", session_id=session_id
        )
        outline_path = output_dir / "outline.json"
        PersistenceHelper.write_json(outline_path, outline)

        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir,
            {"outline": str(outline_path)},
            session_id=session_id,
        )

        logger.info(
            "PaperOutlineGenerator: generated %d sections for idea '%s'",
            len(outline),
            str(idea)[:80],
        )

        return {
            "outline": outline,
            "persistence_info": persistence_info,
        }

    def _build_prompt(self, idea: str, experiment_report: str, references) -> str:
        ref_text = ""
        if references:
            ref_text = "\n".join(
                f"- {r.get('title', '')} ({r.get('year', '')})" for r in references[:20]
            )
        exp_text = ""
        if experiment_report:
            exp_text = f"\nExperiment report:\n{experiment_report}\n"
        return (
            "You are a research paper outline generator. "
            "Given a research idea, produce a structured paper outline.\n"
            "Return ONLY valid JSON: a list of objects, each with keys "
            '"section_type", "title", "bullet_points" (list of strings), '
            '"target_length" (word count as integer).\n\n'
            f"Idea: {idea}\n"
            f"{exp_text}"
            f"References:\n{ref_text}\n"
        )

    def _parse_outline(self, raw: str) -> list:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("PaperOutlineGenerator: failed to parse LLM output as JSON")
            return []
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "outline" in parsed:
            return parsed["outline"]
        return []
