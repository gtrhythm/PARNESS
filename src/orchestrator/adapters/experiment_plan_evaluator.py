import json
import logging
from typing import Any, Dict

from .base import LLMAgentModule

logger = logging.getLogger(__name__)


class ExperimentPlanEvaluatorModule(LLMAgentModule):
    module_name = "experiment_plan_evaluator"

    INPUT_SPEC = {
        "experiment_plan": {"type": "str", "required": False, "default": ""},
        "original_content": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "score": {"type": "float"},
        "evaluation_summary": {"type": "str"},
        "_route": {"type": "str"},
        "_score": {"type": "float"},
        "persistence_info": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.experiment_agents.persistence import PersistenceHelper

        experiment_plan = inputs.get("experiment_plan", "")
        original_content = inputs.get("original_content", "")

        pass_threshold = self.config.get("pass_threshold", 7.0)
        reject_threshold = self.config.get("reject_threshold", 4.0)

        prompt = (
            "You are an expert experiment evaluator. Evaluate the following experiment plan "
            "against the original content/idea.\n\n"
            f"Original content:\n{original_content}\n\n"
            f"Experiment plan:\n{experiment_plan}\n\n"
            "Return a JSON object with keys: "
            '"score" (float 1-10), "summary" (str), "strengths" (list of str), '
            '"weaknesses" (list of str), "recommendations" (list of str).'
        )

        llm_client = self._get_llm_client()
        response = await llm_client.chat(prompt)
        response_text = response if isinstance(response, str) else str(response)

        try:
            evaluation = json.loads(response_text)
        except (json.JSONDecodeError, TypeError):
            evaluation = {"score": 5.0, "summary": response_text}

        score = float(evaluation.get("score", 5.0))

        if score >= pass_threshold:
            route = "pass"
        elif score >= reject_threshold:
            route = "revise"
        else:
            route = "reject"

        output_dir = PersistenceHelper.make_output_dir("experiment_plans", "evaluation")
        eval_path = output_dir / "evaluation.json"
        PersistenceHelper.write_json(eval_path, evaluation)

        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir,
            {"evaluation": str(eval_path)},
        )

        logger.info(
            "ExperimentPlanEvaluator: score=%.2f, route=%s", score, route,
        )

        return {
            "score": score,
            "evaluation_summary": evaluation.get("summary", ""),
            "_route": route,
            "_score": score,
            "persistence_info": persistence_info,
        }
