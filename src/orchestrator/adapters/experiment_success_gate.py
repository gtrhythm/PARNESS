import json
import logging
import os
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class ExperimentSuccessGateModule(BaseModule):
    module_name = "experiment_success_gate"

    INPUT_SPEC = {
        "experiment_results": {"type": "dict", "required": False, "default": {}},
        "execution_log": {"type": "str", "required": False, "default": ""},
        # Optional authoritative success signal from an upstream verifier.
        # When present and not None, overrides the local heuristic on
        # experiment_results + execution_log.
        "success": {"type": "any", "required": False, "default": None},
    }
    OUTPUT_SPEC = {
        "_route": {"type": "str"},
        "retry_count": {"type": "int"},
        "experiment_success": {"type": "bool"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        max_retries = self.config.get("max_retries", 3)
        state_file = self.config.get(
            "state_file",
            "output/auto_idea_to_paper/experiment_gate_state.json",
        )

        experiment_results = inputs.get("experiment_results", {})
        execution_log = inputs.get("execution_log", "")
        verifier_success = inputs.get("success")

        if verifier_success is not None:
            # Authoritative verdict from an upstream verifier (e.g.
            # experiment_verifier_cli). Bypass the local heuristic.
            success = bool(verifier_success)
            logger.info(
                "[ExperimentGate] using upstream verifier verdict: success=%s",
                success,
            )
        else:
            has_results = bool(experiment_results)
            has_error = "ERROR" in (execution_log or "").upper()
            success = has_results and not has_error

        state = self._load_state(state_file)

        if success:
            logger.info("[ExperimentGate] Experiment SUCCESS, passing through")
            state["retry_count"] = 0
            self._save_state(state_file, state)
            return {
                "_route": "pass",
                "retry_count": 0,
                "experiment_success": True,
            }

        state["retry_count"] = state.get("retry_count", 0) + 1
        retry_count = state["retry_count"]

        if retry_count < max_retries:
            logger.info(
                "[ExperimentGate] Experiment FAILED, retry %d/%d",
                retry_count, max_retries,
            )
            self._save_state(state_file, state)
            return {
                "_route": "retry",
                "retry_count": retry_count,
                "experiment_success": False,
            }

        logger.warning(
            "[ExperimentGate] Experiment FAILED after %d retries, skipping",
            max_retries,
        )
        state["retry_count"] = 0
        self._save_state(state_file, state)
        return {
            "_route": "skip",
            "retry_count": max_retries,
            "experiment_success": False,
        }

    @staticmethod
    def _load_state(state_file: str) -> Dict[str, Any]:
        if os.path.exists(state_file):
            try:
                with open(state_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"retry_count": 0}

    @staticmethod
    def _save_state(state_file: str, state: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
        try:
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "[ExperimentGate] Failed to save state: %s", e,
            )
