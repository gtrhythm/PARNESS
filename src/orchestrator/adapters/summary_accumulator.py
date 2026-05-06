import json
import logging
import os
from typing import Any, Dict, List

from .base import BaseModule

logger = logging.getLogger(__name__)


class SummaryAccumulatorModule(BaseModule):
    module_name = "summary_accumulator"

    INPUT_SPEC = {
        "summary": {"type": "str", "required": False, "default": ""},
        "key_innovations": {"type": "list", "required": False, "default": []},
        "open_problems": {"type": "list", "required": False, "default": []},
        "transferable_techniques": {"type": "list", "required": False, "default": []},
        "paper_title": {"type": "str", "required": False, "default": ""},
        "ideas_from_round": {"type": "list", "required": False, "default": []},
        "round_number": {"type": "int", "required": False, "default": 0},
    }
    OUTPUT_SPEC = {
        "_route": {"type": "str"},
        "current_count": {"type": "int"},
        "target_count": {"type": "int"},
        "merged_summaries": {"type": "str"},
        "previous_ideas": {"type": "list"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        target_count = self.config.get("target_count", 3)
        state_file = self.config.get("state_file", "output/auto_idea_to_paper/accumulator_state.json")

        state = self._load_state(state_file)

        ideas_from_round = inputs.get("ideas_from_round", [])
        if ideas_from_round:
            state["previous_ideas"] = ideas_from_round
            state["summaries"] = []
            state["current_count"] = 0

        summary = inputs.get("summary", "")
        if summary:
            entry = {
                "summary": summary,
                "key_innovations": inputs.get("key_innovations", []),
                "open_problems": inputs.get("open_problems", []),
                "transferable_techniques": inputs.get("transferable_techniques", []),
                "paper_title": inputs.get("paper_title", ""),
            }
            state["summaries"].append(entry)
            state["current_count"] = state.get("current_count", 0) + 1

        self._save_state(state_file, state)

        current_count = state.get("current_count", 0)
        if current_count < target_count:
            logger.info(
                "[SummaryAccumulator] Collected %d/%d summaries, need more",
                current_count, target_count,
            )
            return {
                "_route": "need_more",
                "current_count": current_count,
                "target_count": target_count,
                "merged_summaries": "",
                "previous_ideas": state.get("previous_ideas", []),
            }

        merged = self._merge_summaries(state["summaries"])
        if len(merged) > 25000:
            merged = merged[:25000]
        previous_ideas = state.get("previous_ideas", [])

        logger.info(
            "[SummaryAccumulator] Collected %d/%d summaries, ready for idea generation",
            current_count, target_count,
        )

        state["summaries"] = []
        state["current_count"] = 0
        self._save_state(state_file, state)

        return {
            "_route": "ready",
            "current_count": current_count,
            "target_count": target_count,
            "merged_summaries": merged,
            "previous_ideas": previous_ideas,
        }

    @staticmethod
    def _merge_summaries(summaries: List[Dict]) -> str:
        parts = []
        for i, entry in enumerate(summaries, 1):
            section = f"--- Paper {i}: {entry.get('paper_title', 'Unknown')} ---\n"
            section += f"Key Summary: {entry.get('summary', '')}\n"
            if entry.get("key_innovations"):
                section += "Key Innovations:\n"
                for inn in entry["key_innovations"]:
                    section += f"  - {inn}\n"
            if entry.get("open_problems"):
                section += "Open Problems:\n"
                for prob in entry["open_problems"]:
                    section += f"  - {prob}\n"
            if entry.get("transferable_techniques"):
                section += "Transferable Techniques:\n"
                for tech in entry["transferable_techniques"]:
                    section += f"  - {tech}\n"
            parts.append(section)
        return "\n\n".join(parts)

    @staticmethod
    def _load_state(state_file: str) -> Dict[str, Any]:
        if os.path.exists(state_file):
            try:
                with open(state_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "summaries": [],
            "previous_ideas": [],
            "current_count": 0,
        }

    @staticmethod
    def _save_state(state_file: str, state: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
        try:
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.getLogger(__name__).warning("[SummaryAccumulator] Failed to save state: %s", e)
