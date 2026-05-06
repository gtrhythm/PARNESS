import json
import logging
from typing import Any, Dict

from .base import LLMAgentModule

logger = logging.getLogger(__name__)


class ExperimentPlanReviserModule(LLMAgentModule):
    module_name = "experiment_plan_reviser"

    INPUT_SPEC = {
        "experiment_plan": {"type": "str", "required": False, "default": ""},
        "original_content": {"type": "str", "required": False, "default": ""},
        "evaluation_feedback": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "revised_plan": {"type": "str"},
        "persistence_info": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.experiment_agents.persistence import PersistenceHelper

        experiment_plan = inputs.get("experiment_plan", "")
        original_content = inputs.get("original_content", "")
        evaluation_feedback = inputs.get("evaluation_feedback", "")

        prompt = (
            "You are an expert experiment planner. Revise the following experiment plan "
            "based on the evaluation feedback.\n\n"
            f"Original content:\n{original_content}\n\n"
            f"Current experiment plan:\n{experiment_plan}\n\n"
            f"Evaluation feedback:\n{evaluation_feedback}\n\n"
            "Return a JSON object with keys: "
            '"title" (str), "objective" (str), "methodology" (str), '
            '"steps" (list of str), "expected_outcomes" (str), '
            '"metrics" (list of str), "estimated_duration" (str), '
            '"resource_requirements" (dict), "revision_notes" (str).'
        )

        llm_client = self._get_llm_client()
        response = await llm_client.chat(prompt)
        response_text = response if isinstance(response, str) else str(response)

        try:
            revised_data = json.loads(response_text)
        except (json.JSONDecodeError, TypeError):
            revised_data = {"raw_plan": response_text}

        output_dir = PersistenceHelper.make_output_dir("experiment_plans", "revised")
        plan_path = output_dir / "revised_plan.json"
        PersistenceHelper.write_json(plan_path, revised_data)

        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir,
            {"revised_plan": str(plan_path)},
        )

        logger.info("ExperimentPlanReviser: revised plan at %s", plan_path)

        return {
            "revised_plan": json.dumps(revised_data, ensure_ascii=False),
            "persistence_info": persistence_info,
        }
