import json
import logging
import re
from typing import Any, Dict, List

from .base import LLMAgentModule
from src.experiment_agents.persistence import PersistenceHelper

logger = logging.getLogger(__name__)


class CitationInserterModule(LLMAgentModule):
    module_name = "citation_inserter"

    INPUT_SPEC = {
        "paper_sections": {"type": "list", "required": False, "default": []},
        "citation_gaps": {"type": "list", "required": False, "default": []},
        "citation_keys": {"type": "dict", "required": False, "default": {}},
    }
    OUTPUT_SPEC = {
        "annotated_sections": {"type": "list"},
        "persistence_info": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        paper_sections = inputs.get("paper_sections", [])
        citation_gaps = inputs.get("citation_gaps", [])
        citation_keys = inputs.get("citation_keys", {})

        if not paper_sections or not citation_gaps:
            return {
                "annotated_sections": paper_sections,
                "persistence_info": {},
            }

        llm_client = self._get_llm_client()

        gaps_with_refs = [
            g for g in citation_gaps
            if g.get("filled_by") and g.get("filled_by") in citation_keys
        ]

        if not gaps_with_refs:
            return {
                "annotated_sections": paper_sections,
                "persistence_info": {},
            }

        annotated = []
        for section in paper_sections:
            section_name = section.get("section", section.get("title", ""))
            content = section.get("content", section.get("text", ""))

            section_gaps = [
                g for g in gaps_with_refs
                if g.get("section", "") == section_name
            ]

            if not section_gaps:
                annotated.append(dict(section))
                continue

            prompt = (
                "You are a citation insertion assistant. Insert LaTeX \\cite{} commands "
                "into the given text at the appropriate positions.\n\n"
                f"Section: {section_name}\n"
                f"Text:\n{content}\n\n"
                "Citations to insert:\n"
            )
            for g in section_gaps:
                key = citation_keys[g["filled_by"]]
                topic = g.get("required_topic", "")
                context = g.get("context", "")
                prompt += f"- Insert \\cite{{{key}}} near text about '{topic}'"
                if context:
                    prompt += f" (near: '{context[:60]}')"
                prompt += "\n"

            prompt += (
                "\nRules:\n"
                "1. Preserve all existing \\cite{} commands exactly as they are\n"
                "2. Insert new \\cite{} at the most natural position in the sentence\n"
                "3. If multiple citations apply to the same claim, combine: \\cite{key1, key2}\n"
                "4. Return ONLY the modified text, nothing else\n"
                "5. Do not add any explanation or markdown formatting"
            )

            try:
                response = await llm_client.chat(prompt)
                new_content = response.strip()
                if new_content.startswith("```"):
                    new_content = re.sub(r"^```\w*\n?", "", new_content)
                    new_content = re.sub(r"\n?```$", "", new_content)
            except Exception as e:
                logger.warning(
                    "[CitationInserter] LLM failed for section '%s': %s",
                    section_name, e,
                )
                new_content = content

            new_section = dict(section)
            if "content" in new_section:
                new_section["content"] = new_content
            if "text" in new_section:
                new_section["text"] = new_content
            annotated.append(new_section)

        output_dir = PersistenceHelper.make_output_dir(
            "citation_inserter", "annotated"
        )
        PersistenceHelper.write_json(
            output_dir / "annotated_sections.json", annotated
        )
        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir, {"annotated_sections": "annotated_sections.json"}
        )

        logger.info(
            "[CitationInserter] Annotated %d sections with %d citation insertions",
            len(annotated), len(gaps_with_refs),
        )

        return {
            "annotated_sections": annotated,
            "persistence_info": persistence_info,
        }
