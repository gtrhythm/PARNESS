import json
import logging
from typing import Any, Dict

from .base import LLMAgentModule

logger = logging.getLogger(__name__)


class ExperimentResourceCheckerModule(LLMAgentModule):
    module_name = "experiment_resource_checker"

    INPUT_SPEC = {
        "experiment_plan": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "resource_estimate": {"type": "dict"},
        "_route": {"type": "str"},
        "_score": {"type": "float"},
        "persistence_info": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.experiment_agents.persistence import PersistenceHelper
        from src.experiment_agents.resource_config import ResourceConfig

        experiment_plan = inputs.get("experiment_plan", "")
        resource_config_path = self.config.get(
            "resource_config_path", "config/resource_config.yaml"
        )

        rc = ResourceConfig.from_file(resource_config_path)
        resource_summary = rc.summary_text()

        prompt = (
            "You are a resource estimation expert. Given the experiment plan and available "
            "resources, estimate the resources needed and determine execution feasibility.\n\n"
            f"Experiment plan:\n{experiment_plan}\n\n"
            f"Available resources:\n{resource_summary}\n\n"
            "Return a JSON object with keys: "
            '"estimated_cpu_cores" (int), "estimated_memory_gb" (int), '
            '"estimated_gpu_required" (bool), "estimated_gpu_memory_gb" (int), '
            '"estimated_duration_minutes" (int), "estimated_storage_gb" (float), '
            '"can_run_locally" (bool), "needs_external" (bool), '
            '"needs_manual_setup" (bool), "feasibility_notes" (str), '
            '"route" (string: "local" or "external" or "manual").'
        )

        llm_client = self._get_llm_client()
        response = await llm_client.chat(prompt)
        response_text = response if isinstance(response, str) else str(response)

        try:
            estimate = json.loads(response_text)
        except (json.JSONDecodeError, TypeError):
            estimate = {"raw_estimate": response_text}

        route = estimate.get("route", "local")
        if route not in ("local", "external", "manual"):
            if estimate.get("can_run_locally", True):
                route = "local"
            elif estimate.get("needs_external", False):
                route = "external"
            else:
                route = "manual"

        output_dir = PersistenceHelper.make_output_dir("experiment_plans", "resource_check")
        estimate_path = output_dir / "resource_estimate.json"
        PersistenceHelper.write_json(estimate_path, estimate)

        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir,
            {"resource_estimate": str(estimate_path)},
        )

        logger.info(
            "ExperimentResourceChecker: route=%s, estimate at %s",
            route, estimate_path,
        )

        return {
            "resource_estimate": estimate,
            "_route": route,
            "_score": 1.0 if route == "local" else (0.5 if route == "external" else 0.2),
            "persistence_info": persistence_info,
        }
