import logging
from typing import Any, Dict

from .base import LLMAgentModule

logger = logging.getLogger(__name__)

_SECTION_PROMPTS = {
    "abstract": (
        "Write the abstract for this research paper. "
        "Be concise (150-250 words). Summarize the problem, method, key results, and contribution. "
        "Output LaTeX only (no \\begin{document})."
    ),
    "intro": (
        "Write the introduction section. "
        "Cover: problem motivation, prior work context, the gap, and contributions. "
        "Use \\section{Introduction}. Output LaTeX."
    ),
    "method": (
        "Write the method section. "
        "Describe the approach formally, including notation, algorithms, and architecture details. "
        "Use \\section{Method}. Output LaTeX."
    ),
    "experiment": (
        "Write the experimental setup section. "
        "Cover: datasets, baselines, metrics, hyperparameters, and implementation details. "
        "Use \\section{Experiments}. Output LaTeX."
    ),
    "result": (
        "Write the results section. "
        "Present quantitative and qualitative findings with analysis. "
        "Use \\section{Results}. Output LaTeX. Include placeholder tables/figures where appropriate."
    ),
    "discussion": (
        "Write the discussion section. "
        "Analyze results, limitations, and broader impact. "
        "Use \\section{Discussion}. Output LaTeX."
    ),
    "future_work": (
        "Write the future work section. "
        "Suggest concrete extensions and open problems. "
        "Use \\section{Future Work}. Output LaTeX."
    ),
}


class PaperSectionWriterModule(LLMAgentModule):
    module_name = "paper_section_writer"

    INPUT_SPEC = {
        "outline_section": {"type": "dict", "required": False, "default": {}},
        "context": {"type": "str", "required": False, "default": ""},
        "section_type": {"type": "str", "required": False, "default": None},
        "references": {"type": "list", "required": False, "default": []},
        "session_id": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "section_content": {"type": "str"},
        "section_type": {"type": "str"},
        "persistence_info": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.experiment_agents.persistence import PersistenceHelper

        outline_section = inputs.get("outline_section", {})
        context = inputs.get("context", "")
        section_type = inputs.get("section_type") or outline_section.get("section_type", "section")
        references = inputs.get("references") or []

        llm_client = self._get_llm_client()

        prompt = self._build_prompt(outline_section, context, section_type, references)
        raw = await llm_client.chat(prompt)
        section_content = raw.strip()

        session_id = inputs.get("session_id", "")
        output_dir = PersistenceHelper.make_output_dir(
            "paper_section", section_type, session_id=session_id
        )
        content_path = output_dir / f"{section_type}.tex"
        PersistenceHelper.write_text(content_path, section_content)

        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir,
            {section_type: str(content_path)},
            session_id=session_id,
        )

        logger.info(
            "PaperSectionWriter: wrote %s section (%d chars)",
            section_type,
            len(section_content),
        )

        return {
            "section_content": section_content,
            "section_type": section_type,
            "persistence_info": persistence_info,
        }

    def _build_prompt(
        self,
        outline_section: Dict,
        context: str,
        section_type: str,
        references: list,
    ) -> str:
        instruction = _SECTION_PROMPTS.get(section_type, _SECTION_PROMPTS["intro"])
        title = outline_section.get("title", "")
        bullet_points = outline_section.get("bullet_points", [])
        target_length = outline_section.get("target_length", 500)

        bullets_text = "\n".join(f"- {bp}" for bp in bullet_points)
        ref_text = ""
        if references:
            ref_text = "\n".join(
                f"- {r.get('title', '')} ({r.get('year', '')})" for r in references[:15]
            )

        parts = [
            instruction,
            f"\nSection title: {title}",
            f"Target length: ~{target_length} words",
            f"Key points:\n{bullets_text}",
        ]
        if context:
            parts.append(f"\nAdditional context:\n{context}")
        if ref_text:
            parts.append(f"\nReferences to cite:\n{ref_text}")
        return "\n".join(parts)
