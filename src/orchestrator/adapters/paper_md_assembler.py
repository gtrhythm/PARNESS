import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseModule

logger = logging.getLogger(__name__)


class PaperMdAssemblerModule(BaseModule):
    module_name = "paper_md_assembler"

    INPUT_SPEC = {
        "markdown_content": {"type": "any", "required": False, "default": ""},
        "chart_paths": {"type": "list", "required": False, "default": []},
        "idea": {"type": "dict", "required": False, "default": {}},
    }
    OUTPUT_SPEC = {
        "final_md_path": {"type": "str"},
        "final_md_content": {"type": "str"},
        "chart_count": {"type": "int"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        output_dir = self.config.get("output_dir", "output/auto_idea_to_paper")

        content = inputs.get("markdown_content", "")
        if isinstance(content, dict):
            content = content.get("markdown_content", str(content))
        if not isinstance(content, str):
            content = str(content)

        chart_paths = inputs.get("chart_paths", [])
        if not isinstance(chart_paths, list):
            chart_paths = []

        idea = inputs.get("idea", {})
        if not isinstance(idea, dict):
            idea = {}

        idea_title = idea.get("title", "Research Paper")

        chart_section = self._build_chart_section(chart_paths, output_dir)

        if chart_section and "## Results" in content:
            content = content.replace("## Results", f"## Results\n\n{chart_section}\n")
        elif chart_section:
            content += f"\n\n## Figures and Charts\n\n{chart_section}\n"

        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in idea_title[:50])
        safe_title = safe_title.strip().replace(" ", "_") or "paper"
        filename = f"{safe_title}_{timestamp}.md"
        final_path = os.path.join(output_dir, filename)

        with open(final_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(
            "[PaperMdAssembler] Assembled paper at %s (%d chars, %d charts)",
            final_path, len(content), len(chart_paths),
        )

        return {
            "final_md_path": final_path,
            "final_md_content": content,
            "chart_count": len(chart_paths),
        }

    @staticmethod
    def _build_chart_section(chart_paths: List[str], output_dir: str) -> str:
        if not chart_paths:
            return ""

        lines = []
        for i, path in enumerate(chart_paths):
            p = Path(path)
            name = p.stem.replace("_", " ").title()
            rel_path = os.path.relpath(path, output_dir) if os.path.isabs(path) else path
            lines.append(f"### Figure {i + 1}: {name}\n")
            lines.append(f"![{name}]({rel_path})\n")
            lines.append("")

        return "\n".join(lines)
