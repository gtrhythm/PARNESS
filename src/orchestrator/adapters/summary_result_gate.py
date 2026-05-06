import logging
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class SummaryResultGateModule(BaseModule):
    """Check whether paper_summary_search returned valid metadata.

    Input:
        metadata: Dict — from paper_summary_search (PaperContent.to_dict())
        source: str — which source matched

    Output:
        _route: "success" | "fail"
        metadata: Dict — forwarded
        source: str — forwarded
        paper_id: str — forwarded
    """

    module_name = "summary_result_gate"

    INPUT_SPEC = {
        "metadata": {"type": "dict", "required": False, "default": {}},
        "source": {"type": "str", "required": False, "default": ""},
        "paper_id": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "_route": {"type": "str"},
        "metadata": {"type": "dict"},
        "source": {"type": "str"},
        "paper_id": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        metadata = inputs.get("metadata", {})
        source = inputs.get("source", "")
        paper_id = inputs.get("paper_id", "")

        if not metadata or not isinstance(metadata, dict):
            logger.info("SummaryResultGate: FAIL (empty metadata)")
            return {"_route": "fail", "metadata": {}, "source": "", "paper_id": paper_id}

        title = metadata.get("title", "")
        abstract = metadata.get("abstract", "")

        if title or abstract:
            logger.info(
                "SummaryResultGate: SUCCESS source=%s title='%s'",
                source, (title or "")[:80],
            )
            return {
                "_route": "success",
                "metadata": metadata,
                "source": source,
                "paper_id": paper_id,
            }

        logger.info("SummaryResultGate: FAIL (no title or abstract)")
        return {"_route": "fail", "metadata": {}, "source": "", "paper_id": paper_id}
