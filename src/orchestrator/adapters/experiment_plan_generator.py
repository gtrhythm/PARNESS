import json
import logging
from typing import Any, Dict

from .base import LLMAgentModule

logger = logging.getLogger(__name__)


class ExperimentPlanGeneratorModule(LLMAgentModule):
    module_name = "experiment_plan_generator"

    INPUT_SPEC = {
        "content": {"type": "str", "required": False, "default": ""},
        "content_type": {"type": "str", "required": False, "default": "idea"},
        "feedback": {"type": "str", "required": False, "default": ""},
        "resource_config_path": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "experiment_plan": {"type": "str"},
        "persistence_info": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.experiment_agents.persistence import PersistenceHelper

        content = inputs.get("content", "")
        content_type = inputs.get("content_type", "idea")
        feedback = inputs.get("feedback", "")
        resource_config_path = inputs.get("resource_config_path", "")

        resource_context = ""
        if resource_config_path:
            from src.experiment_agents.resource_config import ResourceConfig
            rc = ResourceConfig.from_file(resource_config_path)
            resource_context = f"\n\nAvailable resources:\n{rc.summary_text()}"

        feedback_section = ""
        if feedback:
            feedback_section = f"\n\nPrevious feedback to address:\n{feedback}"

        prompt = (
            f"You are an expert experiment planner. Given the following {content_type}, "
            f"generate a detailed experiment plan in JSON format.\n\n"
            f"Content:\n{content}"
            f"{resource_context}"
            f"{feedback_section}\n\n"
            f"Return a JSON object with keys: "
            f'"title" (str), "objective" (str), "methodology" (str), '
            f'"steps" (list of str), "expected_outcomes" (str), '
            f'"metrics" (list of str), "estimated_duration" (str), '
            f'"resource_requirements" (dict).'
        )

        llm_client = self._get_llm_client()
        response = await llm_client.chat(prompt)
        plan_text = response if isinstance(response, str) else str(response)

        try:
            plan_data = json.loads(plan_text)
        except (json.JSONDecodeError, TypeError):
            plan_data = {"raw_plan": plan_text}

        output_dir = PersistenceHelper.make_output_dir("experiment_plans", "plan")
        plan_path = output_dir / "experiment_plan.json"
        PersistenceHelper.write_json(plan_path, plan_data)

        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir,
            {"experiment_plan": str(plan_path)},
        )

        logger.info("ExperimentPlanGenerator: plan generated at %s", plan_path)

        return {
            "experiment_plan": json.dumps(plan_data, ensure_ascii=False),
            "persistence_info": persistence_info,
        }
