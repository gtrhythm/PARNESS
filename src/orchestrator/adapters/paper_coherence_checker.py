import json
import logging
from typing import Any, Dict

from .base import LLMAgentModule

logger = logging.getLogger(__name__)


class PaperCoherenceCheckerModule(LLMAgentModule):
    module_name = "paper_coherence_checker"

    INPUT_SPEC = {
        "all_sections": {"type": "list", "required": False, "default": []},
        "outline": {"type": "list", "required": False, "default": []},
        "session_id": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "issues": {"type": "list"},
        "_route": {"type": "str"},
        "_score": {"type": "float"},
        "persistence_info": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.experiment_agents.persistence import PersistenceHelper

        all_sections = inputs.get("all_sections", [])
        outline = inputs.get("outline", [])

        llm_client = self._get_llm_client()

        prompt = self._build_prompt(all_sections, outline)
        raw = await llm_client.chat(prompt)
        result = self._parse_result(raw)

        issues = result.get("issues", [])
        score = result.get("score", 0.0)

        route = "pass" if score >= 7.0 else "fix"

        session_id = inputs.get("session_id", "")
        output_dir = PersistenceHelper.make_output_dir(
            "paper_coherence", "check", session_id=session_id
        )
        report_path = output_dir / "coherence_report.json"
        PersistenceHelper.write_json(report_path, result)

        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir,
            {"report": str(report_path)},
            session_id=session_id,
        )

        logger.info(
            "PaperCoherenceChecker: score=%.2f, route=%s, %d issues",
            score,
            route,
            len(issues),
        )

        return {
            "issues": issues,
            "_route": route,
            "_score": score,
            "persistence_info": persistence_info,
        }

    def _build_prompt(self, all_sections: list, outline: list) -> str:
        sections_text = ""
        for sec in all_sections:
            st = sec.get("section_type", "")
            title = sec.get("title", "")
            content = sec.get("content", sec.get("section_content", ""))
            sections_text += f"\n--- {st}: {title} ---\n{content[:1500]}\n"

        outline_text = json.dumps(outline[:10], ensure_ascii=False) if outline else "N/A"

        return (
            "You are a paper coherence checker. Analyze the following paper sections "
            "for consistency and logical flow.\n\n"
            "Check:\n"
            "1. Method ↔ Experiment alignment\n"
            "2. Introduction ↔ Results consistency\n"
            "3. Terminology consistency across sections\n"
            "4. Data/number consistency\n"
            "5. Logical flow between sections\n\n"
            f"Outline:\n{outline_text}\n\n"
            f"Sections:\n{sections_text}\n\n"
            "Return ONLY valid JSON with keys:\n"
            '- "issues": list of objects, each with "section", "issue_type", '
            '"description", "suggestion"\n'
            '- "score": float 0-10 overall coherence score\n'
        )

    def _parse_result(self, raw: str) -> Dict:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("PaperCoherenceChecker: failed to parse LLM output")
            return {"issues": [], "score": 0.0}
        return {
            "issues": parsed.get("issues", []),
            "score": float(parsed.get("score", 0.0)),
        }
