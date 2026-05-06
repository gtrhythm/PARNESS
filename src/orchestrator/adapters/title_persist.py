import logging
from pathlib import Path
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class TitlePersistModule(BaseModule):
    """Write the validated paper title to ``<folder>/title.md``.

    Sits right after ``title_result_gate`` succeeds so the title is
    captured to disk before any downstream search / persist work is
    attempted (and before the original parse folder might be moved
    elsewhere).

    Input:
        folder_path: str — paper's parsed-result folder
        title:       str — validated title from title_result_gate
        paper_id:    str — for logging only

    Output:
        title_path: str — written file path (or "" on failure)
        wrote:      bool
    """

    module_name = "title_persist"

    INPUT_SPEC = {
        "folder_path": {"type": "str", "required": True, "default": ""},
        "title": {"type": "str", "required": True, "default": ""},
        "paper_id": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "title_path": {"type": "str"},
        "wrote": {"type": "bool"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        folder_path = (inputs.get("folder_path") or "").strip()
        title = (inputs.get("title") or "").strip()
        paper_id = inputs.get("paper_id") or ""
        filename = self.config.get("filename", "title.md")

        if not folder_path or not title:
            logger.warning(
                "TitlePersist: skipped (folder_path=%r, title=%r)",
                folder_path[:60], title[:60],
            )
            return {"title_path": "", "wrote": False}

        folder = Path(folder_path)
        if not folder.is_dir():
            logger.warning("TitlePersist: folder not found: %s", folder)
            return {"title_path": "", "wrote": False}

        target = folder / filename
        try:
            target.write_text(title + "\n", encoding="utf-8")
        except Exception as e:
            logger.warning("TitlePersist: write failed for %s: %s", target, e)
            return {"title_path": "", "wrote": False}

        logger.info(
            "TitlePersist: wrote %s (paper_id=%s)", target, paper_id,
        )
        return {"title_path": str(target), "wrote": True}
