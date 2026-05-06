import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .base import BaseModule

logger = logging.getLogger(__name__)


class PDFQueueFeederModule(BaseModule):
    """Dispatch PDF paths one at a time from a persistent queue.

    Wraps :class:`PDFQueueAgent <src.pdf_queue.agent.PDFQueueAgent>`.

    Params:
        pdf_list_path: str — JSON file with PDF paths
        pdf_list: List[str] — inline PDF paths (alternative to pdf_list_path)
        state_dir: str — directory for queue_state.json

    Output:
        pdf_files: List[str] — single-element list ``[path]``
        pdf_path: str — the dispatched path
        queue_index: int — 0-based dispatch index
        queue_remaining: int — items left after this dispatch
        _route: "has_next" | "exhausted"
    """

    module_name = "pdf_queue_feeder"

    INPUT_SPEC = {
        "pdf_list_path": {"type": "str", "required": False, "default": ""},
        "pdf_list": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "pdf_files": {"type": "list"},
        "pdf_path": {"type": "str"},
        "queue_index": {"type": "int"},
        "queue_remaining": {"type": "int"},
        "_route": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._agent = None

    def _get_agent(self):
        if self._agent is not None:
            return self._agent

        from src.pdf_queue.agent import PDFQueueAgent

        state_dir = self.config.get("state_dir", "output/pdf_queue")
        pdf_list_path = self.config.get("pdf_list_path", "")
        pdf_list = self.config.get("pdf_list", [])

        if pdf_list_path:
            agent = PDFQueueAgent.from_json(pdf_list_path, state_dir=state_dir)
        elif pdf_list:
            agent = PDFQueueAgent.from_list(pdf_list, state_dir=state_dir)
        else:
            agent = PDFQueueAgent.resume(state_dir=state_dir)

        self._agent = agent
        return agent

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        pdf_list_path = inputs.get("pdf_list_path", "")
        pdf_list = inputs.get("pdf_list", [])

        if pdf_list_path or pdf_list:
            state_dir = self.config.get("state_dir", "output/pdf_queue")
            from src.pdf_queue.agent import PDFQueueAgent
            if pdf_list_path:
                self._agent = PDFQueueAgent.from_json(pdf_list_path, state_dir=state_dir)
            else:
                self._agent = PDFQueueAgent.from_list(pdf_list, state_dir=state_dir)

        agent = self._get_agent()

        if not agent.has_next():
            logger.info("PDFQueueFeeder: queue exhausted")
            return {
                "pdf_files": [],
                "pdf_path": "",
                "queue_index": -1,
                "queue_remaining": 0,
                "_route": "exhausted",
            }

        result = agent.next()
        if result is None:
            return {
                "pdf_files": [],
                "pdf_path": "",
                "queue_index": -1,
                "queue_remaining": 0,
                "_route": "exhausted",
            }

        path = result["path"]
        index = result["index"]
        remaining = agent.progress().get("remaining", 0) - 1
        remaining = max(0, remaining)

        logger.info(
            "PDFQueueFeeder: dispatched [%d] %s (remaining: %d)",
            index, path, remaining,
        )

        return {
            "pdf_files": [path],
            "pdf_path": path,
            "queue_index": index,
            "queue_remaining": remaining,
            "_route": "has_next",
        }
