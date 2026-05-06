import logging
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class ParseResultGateModule(BaseModule):
    """Check whether pdf_kit_parse produced valid results.

    Input:
        parsed_papers: List[Dict] — from pdf_kit_parse
        parse_errors: List[Dict] — from pdf_kit_parse

    Output:
        _route: "success" | "fail"
        parsed_papers: List[Dict] — forwarded
        paper_id: str — first paper's paper_id
    """

    module_name = "parse_result_gate"

    INPUT_SPEC = {
        "parsed_papers": {"type": "list", "required": False, "default": []},
        "parse_errors": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "_route": {"type": "str"},
        "parsed_papers": {"type": "list"},
        "paper_id": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        parsed = inputs.get("parsed_papers", [])
        errors = inputs.get("parse_errors", [])

        if parsed and len(errors) == 0:
            paper = parsed[0] if isinstance(parsed[0], dict) else {}
            paper_id = paper.get("paper_id", "")
            logger.info("ParseResultGate: SUCCESS paper_id=%s", paper_id)
            return {
                "_route": "success",
                "parsed_papers": parsed,
                "paper_id": paper_id,
            }

        logger.info(
            "ParseResultGate: FAIL (parsed=%d, errors=%d)",
            len(parsed), len(errors),
        )
        return {
            "_route": "fail",
            "parsed_papers": parsed,
            "paper_id": "",
        }
