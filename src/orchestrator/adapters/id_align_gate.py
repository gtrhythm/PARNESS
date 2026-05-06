import logging
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class IDAlignGateModule(BaseModule):
    """Align paper_id between parse result and search result.

    pdf_kit_parse uses file stem (e.g. ``2604.04433``) as paper_id,
    while search returns ``s2:xxxxx`` or similar.  This gate rewrites
    the search metadata's paper_id to the parse paper_id so that
    ``summary_persist`` updates the correct row via ``ON CONFLICT``.

    Input:
        metadata: Dict — from search (PaperContent.to_dict())
        paper_id: str — parse paper_id (file stem)

    Output:
        metadata: Dict — with paper_id rewritten to parse paper_id
        paper_id: str — parse paper_id
        original_paper_id: str — the search source's paper_id
    """

    module_name = "id_align_gate"

    INPUT_SPEC = {
        "metadata": {"type": "dict", "required": False, "default": {}},
        "paper_id": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "dict"},
        "paper_id": {"type": "str"},
        "original_paper_id": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        metadata = inputs.get("metadata", {})
        parse_paper_id = inputs.get("paper_id", "")

        if not metadata or not parse_paper_id:
            logger.info("IDAlignGate: missing metadata or paper_id, passing through")
            return {
                "metadata": metadata,
                "paper_id": parse_paper_id,
                "original_paper_id": "",
            }

        original_pid = metadata.get("paper_id", "")

        if original_pid != parse_paper_id:
            metadata = dict(metadata)
            metadata["paper_id"] = parse_paper_id
            logger.info(
                "IDAlignGate: %s -> %s", original_pid, parse_paper_id,
            )

        return {
            "metadata": metadata,
            "paper_id": parse_paper_id,
            "original_paper_id": original_pid,
        }
