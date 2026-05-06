import logging
import uuid
from pathlib import Path
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class PaperFormatterModule(BaseModule):
    module_name = "paper_formatter"

    INPUT_SPEC = {
        "all_sections": {"type": "list", "required": False, "default": []},
        "images": {"type": "list", "required": False, "default": []},
        "bibtex": {"type": "str", "required": False, "default": ""},
        "template": {"type": "str", "required": False, "default": "iclr"},
        "session_id": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "tex_path": {"type": "str"},
        "pdf_path": {"type": "str"},
        "persistence_info": {"type": "dict"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.experiment_agents.persistence import PersistenceHelper

        all_sections = inputs.get("all_sections", [])
        images = inputs.get("images") or []
        bibtex = inputs.get("bibtex", "")
        template = inputs.get("template", "iclr")
        formatter_mode = self.config.get("formatter_mode", "direct")

        session_id = inputs.get("session_id", "")
        output_dir = PersistenceHelper.make_output_dir(
            "paper_format", template, session_id=session_id
        )

        tex_content = ""
        if formatter_mode == "direct":
            tex_content = self._assemble_tex(all_sections, images, bibtex, template)

        tex_path = output_dir / "paper.tex"
        PersistenceHelper.write_text(tex_path, tex_content)

        if bibtex:
            bib_path = output_dir / "references.bib"
            PersistenceHelper.write_text(bib_path, bibtex)

        pdf_path = ""

        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir,
            {"tex": str(tex_path), "pdf": pdf_path},
            session_id=session_id,
        )

        logger.info(
            "PaperFormatter: mode=%s, template=%s, tex=%s",
            formatter_mode,
            template,
            str(tex_path),
        )

        return {
            "tex_path": str(tex_path),
            "pdf_path": pdf_path,
            "persistence_info": persistence_info,
        }

    @staticmethod
    def _assemble_tex(sections, images, bibtex_content, template):
        parts = [r"\documentclass{article}", r"\usepackage{graphicx}", r"\usepackage{natbib}", ""]
        if bibtex_content:
            parts.append(r"\bibliographystyle{plain}")
        parts.append(r"\begin{document}")
        for sec in sections:
            title = sec.get("title", "")
            content = sec.get("content", sec.get("section_content", ""))
            parts.append(f"\\section{{{title}}}")
            parts.append(content)
            parts.append("")
        if images:
            for img in images:
                path = img.get("path", "")
                caption = img.get("caption", "")
                label = img.get("label", "")
                if path:
                    parts.append(r"\begin{figure}[htbp]")
                    parts.append(f"\\centering\\includegraphics{{{path}}}")
                    parts.append(f"\\caption{{{caption}}}")
                    if label:
                        parts.append(f"\\label{{{label}}}")
                    parts.append(r"\end{figure}")
        if bibtex_content:
            parts.append(r"\bibliography{references}")
        parts.append(r"\end{document}")
        return "\n".join(parts)
