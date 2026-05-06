import logging
from pathlib import Path
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class TitleLoaderModule(BaseModule):
    """Read the persisted title from ``<folder>/title.md``.

    Used by the DB persistence layer so it doesn't have to re-run the
    LLM title extractor: layer 2 already wrote the validated title to
    disk.
    """

    module_name = "title_loader"

    INPUT_SPEC = {
        "folder_path": {"type": "str", "required": True, "default": ""},
        "paper_id": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "title": {"type": "str"},
        "paper_id": {"type": "str"},
        "_route": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        folder_path = (inputs.get("folder_path") or "").strip()
        paper_id = (inputs.get("paper_id") or "").strip()
        filename = self.config.get("filename", "title.md")

        if not folder_path:
            return {"title": "", "paper_id": paper_id, "_route": "fail"}

        target = Path(folder_path) / filename
        if not target.is_file():
            logger.info("TitleLoader: no title file at %s", target)
            return {"title": "", "paper_id": paper_id, "_route": "fail"}

        try:
            title = target.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning("TitleLoader: failed to read %s: %s", target, e)
            return {"title": "", "paper_id": paper_id, "_route": "fail"}

        if not paper_id:
            id_file = Path(folder_path) / "paper_id.txt"
            if id_file.is_file():
                try:
                    paper_id = id_file.read_text(encoding="utf-8").strip()
                except Exception:
                    pass
            if not paper_id:
                paper_id = Path(folder_path).name

        if not title:
            return {"title": "", "paper_id": paper_id, "_route": "fail"}

        logger.info(
            "TitleLoader: paper_id=%s title='%s'", paper_id, title[:80],
        )
        return {"title": title, "paper_id": paper_id, "_route": "ok"}
