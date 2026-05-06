import json
import logging
import os
from datetime import datetime
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class IdeaSaverModule(BaseModule):
    """Save accepted idea to local file, named by save timestamp.

    Params:
        output_dir: str — directory to save ideas (default: output/accepted_ideas)

    Input:
        idea: Dict — the idea to save
        overall_score: float — the idea's score

    Output:
        save_success: bool
        saved_path: str — file path of saved idea
        idea_title: str
    """

    INPUT_SPEC = {
        "idea": {"type": "dict", "required": False, "default": {}},
        "overall_score": {"type": "float", "required": False, "default": 0.0},
    }
    OUTPUT_SPEC = {
        "save_success": {"type": "bool"},
        "saved_path": {"type": "str"},
        "idea_title": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        output_dir = self.config.get("output_dir", "output/accepted_ideas")
        idea = inputs.get("idea", {})
        score = inputs.get("overall_score", 0.0)

        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        title = idea.get("title", "untitled")
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)[:60]
        filename = f"idea_{timestamp}_{safe_title}.json"
        filepath = os.path.join(output_dir, filename)

        save_data = {
            "saved_at": datetime.now().isoformat(),
            "overall_score": score,
            "idea": idea,
        }

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False, default=str)
            logger.info("[IdeaSaver] Saved idea to %s", filepath)
            return {
                "save_success": True,
                "saved_path": filepath,
                "idea_title": title,
                "overall_score": score,
                "idea": idea,
            }
        except Exception as e:
            logger.error("[IdeaSaver] Failed to save idea: %s", e)
            return {
                "save_success": False,
                "saved_path": "",
                "idea_title": title,
                "overall_score": score,
                "idea": idea,
                "error": str(e),
            }
