import json
import logging
from typing import Any, Dict, List

from .base import LLMAgentModule
from src.experiment_agents.persistence import PersistenceHelper

logger = logging.getLogger(__name__)


class ReferenceGapAnalyzerModule(LLMAgentModule):
    module_name = "reference_gap_analyzer"

    INPUT_SPEC = {
        "paper_sections": {"type": "list", "required": False, "default": []},
        "candidate_references": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "citation_gaps": {"type": "list"},
        "persistence_info": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        paper_sections = inputs.get("paper_sections", [])
        candidate_references = inputs.get("candidate_references", [])

        if not paper_sections:
            return {
                "citation_gaps": [],
                "persistence_info": {},
            }

        llm_client = self._get_llm_client()

        sections_summary = self._build_sections_summary(paper_sections)
        refs_summary = self._build_refs_summary(candidate_references)

        prompt = (
            "You are a citation gap analyzer. Given paper sections and a list of candidate references, "
            "identify where citations are needed.\n\n"
            "For each location that needs a citation, provide:\n"
            '- "section": the section name\n'
            '- "context": a brief quote of the surrounding text (max 100 chars)\n'
            '- "required_topic": what topic the citation should cover\n'
            '- "filled_by": the paper_id of the best matching candidate, or null if none fits\n'
            '- "is_original": true if the text already contains a \\cite{} command\n\n'
            "Paper sections:\n"
            f"{sections_summary}\n\n"
            "Candidate references:\n"
            f"{refs_summary}\n\n"
            "Return a JSON array of gap objects. Respond ONLY with valid JSON, no markdown."
        )

        response = await llm_client.chat(prompt)
        citation_gaps = self._parse_response(response, paper_sections)

        output_dir = PersistenceHelper.make_output_dir(
            "reference_gap_analyzer", "gaps"
        )
        PersistenceHelper.write_json(
            output_dir / "citation_gaps.json", citation_gaps
        )
        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir, {"citation_gaps": "citation_gaps.json"}
        )

        logger.info(
            "[ReferenceGapAnalyzer] Found %d citation gaps",
            len(citation_gaps),
        )

        return {
            "citation_gaps": citation_gaps,
            "persistence_info": persistence_info,
        }

    @staticmethod
    def _build_sections_summary(sections: List[Dict]) -> str:
        parts = []
        for s in sections:
            name = s.get("section", s.get("title", "unknown"))
            content = s.get("content", s.get("text", ""))
            if len(content) > 500:
                content = content[:500] + "..."
            parts.append(f"[{name}]: {content}")
        return "\n---\n".join(parts)

    @staticmethod
    def _build_refs_summary(refs: List[Dict]) -> str:
        parts = []
        for r in refs:
            pid = r.get("paper_id", "?")
            title = r.get("title", "")
            venue = r.get("venue", "")
            year = r.get("year", "")
            abstract = r.get("abstract", "")
            if len(abstract) > 200:
                abstract = abstract[:200] + "..."
            parts.append(f"paper_id={pid} | {title} ({year}, {venue}): {abstract}")
        return "\n".join(parts)

    def _parse_response(
        self, response: str, paper_sections: List[Dict]
    ) -> List[Dict]:
        try:
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            gaps = json.loads(text)
            if not isinstance(gaps, list):
                gaps = [gaps]
        except (json.JSONDecodeError, IndexError):
            logger.warning(
                "[ReferenceGapAnalyzer] Failed to parse LLM response, returning empty gaps"
            )
            gaps = []

        original_set = set()
        for s in paper_sections:
            content = s.get("content", s.get("text", ""))
            if "\\cite{" in content:
                section_name = s.get("section", s.get("title", "unknown"))
                original_set.add(section_name)

        for g in gaps:
            if "is_original" not in g:
                section = g.get("section", "")
                g["is_original"] = section in original_set or "\\cite{" in g.get("context", "")
            if "filled_by" not in g:
                g["filled_by"] = None

        return gaps
