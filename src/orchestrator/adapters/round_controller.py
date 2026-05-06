import json
import logging
import os
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class RoundControllerModule(BaseModule):
    module_name = "round_controller"

    INPUT_SPEC = {
        "ideas": {"type": "list", "required": False, "default": []},
        "round_report": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "_route": {"type": "str"},
        "ideas": {"type": "list"},
        "round_number": {"type": "int"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        max_rounds = self.config.get("max_rounds", 10)
        state_file = self.config.get("state_file", "output/auto_idea_to_paper/round_state.json")
        accumulator_state_file = self.config.get(
            "accumulator_state_file",
            "output/auto_idea_to_paper/accumulator_state.json",
        )

        ideas = inputs.get("ideas", [])
        if not isinstance(ideas, list):
            ideas = []

        state = self._load_state(state_file)
        state["round_number"] = state.get("round_number", 0) + 1
        state["current_ideas"] = ideas
        self._save_state(state_file, state)

        round_number = state["round_number"]

        self._update_accumulator_previous_ideas(accumulator_state_file, ideas)

        if round_number >= max_rounds:
            logger.info(
                "[RoundController] Round %d/%d: EXIT with %d ideas",
                round_number, max_rounds, len(ideas),
            )
            return {
                "_route": "exit",
                "ideas": ideas,
                "round_number": round_number,
            }

        logger.info(
            "[RoundController] Round %d/%d: CONTINUE with %d ideas",
            round_number, max_rounds, len(ideas),
        )
        return {
            "_route": "continue",
            "ideas": ideas,
            "round_number": round_number,
        }

    @staticmethod
    def _update_accumulator_previous_ideas(accumulator_state_file: str, ideas: list) -> None:
        if not os.path.exists(accumulator_state_file):
            state = {"summaries": [], "previous_ideas": [], "current_count": 0}
        else:
            try:
                with open(accumulator_state_file, "r") as f:
                    state = json.load(f)
            except Exception:
                state = {"summaries": [], "previous_ideas": [], "current_count": 0}

        state["previous_ideas"] = ideas
        state["summaries"] = []
        state["current_count"] = 0

        os.makedirs(os.path.dirname(accumulator_state_file) or ".", exist_ok=True)
        try:
            with open(accumulator_state_file, "w") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "[RoundController] Failed to update accumulator state: %s", e
            )

    @staticmethod
    def _load_state(state_file: str) -> Dict[str, Any]:
        if os.path.exists(state_file):
            try:
                with open(state_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"round_number": 0, "current_ideas": []}

    @staticmethod
    def _save_state(state_file: str, state: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
        try:
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.getLogger(__name__).warning("[RoundController] Failed to save state: %s", e)
