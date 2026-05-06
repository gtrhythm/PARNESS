import json
import logging
import os
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class IdeaCounterModule(BaseModule):
    """Count accepted ideas and control the iteration loop.

    - If judge_decision is "accept" and count < target: _route = "continue"
    - If judge_decision is "accept" and count >= target: _route = "exit"
    - If judge_decision is "reject": _route = "continue" (retry with new papers)

    Params:
        target_count: int — target number of ideas to generate (default: 50)
        state_file: str — path to persist counter state (default: output/idea_counter_state.json)

    Input:
        judge_decision: str — "accept" or "reject" (from idea_judge)
        save_success: bool — optional, from idea_saver (for logging only)

    Output:
        _route: "continue" | "exit"
        accepted_count: int — total accepted ideas so far
        target_count: int
        total_iterations: int — total iterations (accept + reject)
    """

    INPUT_SPEC = {
        "judge_decision": {"type": "str", "required": False, "default": ""},
        "save_success": {"type": "bool", "required": False, "default": False},
    }
    OUTPUT_SPEC = {
        "_route": {"type": "str"},
        "accepted_count": {"type": "int"},
        "target_count": {"type": "int"},
        "total_iterations": {"type": "int"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        target_count = self.config.get("target_count", 50)
        state_file = self.config.get("state_file", "output/idea_counter_state.json")

        judge_decision = inputs.get("judge_decision", "")
        save_success = inputs.get("save_success", False)

        state = self._load_state(state_file)

        if judge_decision == "accept":
            state["accepted_count"] = state.get("accepted_count", 0) + 1

        state["total_iterations"] = state.get("total_iterations", 0) + 1
        self._save_state(state_file, state)

        accepted_count = state.get("accepted_count", 0)
        total_iterations = state.get("total_iterations", 0)

        if accepted_count >= target_count:
            route = "exit"
            logger.info(
                "[IdeaCounter] EXIT: accepted %d/%d ideas (total iterations: %d)",
                accepted_count, target_count, total_iterations,
            )
        else:
            route = "continue"
            logger.info(
                "[IdeaCounter] CONTINUE: accepted %d/%d ideas (total iterations: %d, last: %s)",
                accepted_count, target_count, total_iterations,
                "accepted" if judge_decision == "accept" else "rejected",
            )

        return {
            "_route": route,
            "accepted_count": accepted_count,
            "target_count": target_count,
            "total_iterations": total_iterations,
        }

    @staticmethod
    def _load_state(state_file: str) -> Dict[str, Any]:
        if os.path.exists(state_file):
            try:
                with open(state_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"accepted_count": 0, "total_iterations": 0}

    @staticmethod
    def _save_state(state_file: str, state: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
        try:
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logging.getLogger(__name__).warning("[IdeaCounter] Failed to save state: %s", e)
