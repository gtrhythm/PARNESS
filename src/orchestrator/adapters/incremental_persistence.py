import json
import logging
import os
from datetime import datetime
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class IncrementalPersistenceModule(BaseModule):
    module_name = "incremental_persistence"

    INPUT_SPEC = {
        "data": {"type": "any", "required": False, "default": None},
    }
    OUTPUT_SPEC = {
        "persisted": {"type": "bool"},
        "file_path": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        file_path = self.config.get(
            "file_path",
            "output/auto_idea_to_paper/pipeline_state.jsonl",
        )
        source = self.config.get("source", "unknown")
        data = inputs.get("data")

        if data is None:
            logger.debug("[Persist] No data for source=%s", source)
            return {"persisted": False, "file_path": file_path}

        entry = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "type": type(data).__name__,
        }

        if isinstance(data, dict):
            entry["data"] = data
        elif isinstance(data, str):
            if len(data) > 50000:
                data = data[:50000] + "...[truncated]"
            entry["data"] = data
        elif isinstance(data, list):
            entry["count"] = len(data)
            entry["data"] = data[:100] if len(data) > 100 else data
        else:
            entry["data"] = str(data)[:5000]

        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)

        try:
            line = json.dumps(entry, ensure_ascii=False, default=str)
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            logger.info(
                "[Persist] %s → %s (%d bytes)",
                source, os.path.basename(file_path), len(line),
            )
            return {"persisted": True, "file_path": file_path}
        except Exception as e:
            logger.warning("[Persist] FAILED for %s: %s", source, e)
            return {"persisted": False, "file_path": file_path}
