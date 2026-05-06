import logging
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class TitleResultGateModule(BaseModule):
    """Check whether title_extractor produced a valid title.

    Input:
        titles: List[Dict] — from title_extractor, each has {paper_id, title, status}

    Output:
        _route: "success" | "fail"
        validated_title: str — the extracted title
        paper_id: str — forwarded
    """

    module_name = "title_result_gate"

    INPUT_SPEC = {
        "titles": {"type": "list", "required": False, "default": []},
        "paper_id": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "_route": {"type": "str"},
        "validated_title": {"type": "str"},
        "paper_id": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        titles = inputs.get("titles", [])
        paper_id = inputs.get("paper_id", "")

        if not titles:
            logger.info("TitleResultGate: FAIL (no titles)")
            return {"_route": "fail", "validated_title": "", "paper_id": paper_id}

        first = titles[0] if isinstance(titles[0], dict) else {}
        title = first.get("title", "")
        status = first.get("status", "fail")

        if title and status == "success":
            logger.info("TitleResultGate: SUCCESS title='%s'", title[:80])
            return {
                "_route": "success",
                "validated_title": title,
                "paper_id": first.get("paper_id", paper_id),
            }

        logger.info("TitleResultGate: FAIL (status=%s, title='%s')", status, (title or "")[:60])
        return {"_route": "fail", "validated_title": "", "paper_id": paper_id}
