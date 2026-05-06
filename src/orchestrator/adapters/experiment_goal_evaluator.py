import json
import logging
from typing import Any, Dict

from .base import LLMAgentModule

logger = logging.getLogger(__name__)


class ExperimentGoalEvaluatorModule(LLMAgentModule):
    module_name = "experiment_goal_evaluator"

    INPUT_SPEC = {
        "idea": {"type": "str", "required": False, "default": ""},
        "experiment_plan": {"type": "str", "required": False, "default": ""},
        "experiment_results": {"type": "dict", "required": False, "default": {}},
    }
    OUTPUT_SPEC = {
        "evaluation": {"type": "str"},
        "suggestions": {"type": "str"},
        "_route": {"type": "str"},
        "_score": {"type": "float"},
        "persistence_info": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.experiment_agents.persistence import PersistenceHelper

        idea = inputs.get("idea", "")
        experiment_plan = inputs.get("experiment_plan", "")
        experiment_results = inputs.get("experiment_results", {})
        pass_threshold = self.config.get("pass_threshold", 6.0)

        prompt = (
            "You are an expert experiment evaluator. Evaluate whether the experiment results "
            "achieve the goals stated in the original idea and experiment plan.\n\n"
            f"Original idea:\n{idea}\n\n"
            f"Experiment plan:\n{experiment_plan}\n\n"
            f"Experiment results:\n{json.dumps(experiment_results, ensure_ascii=False, indent=2)}\n\n"
            "Return a JSON object with keys: "
            '"evaluation" (str - detailed evaluation), '
            '"score" (float 1-10), '
            '"suggestions" (str - suggestions for improvement if any), '
            '"goal_achieved" (bool), '
            '"key_findings" (list of str).'
        )

        llm_client = self._get_llm_client()
        response = await llm_client.chat(prompt)
        response_text = response if isinstance(response, str) else str(response)

        try:
            evaluation_data = json.loads(response_text)
        except (json.JSONDecodeError, TypeError):
            evaluation_data = {"evaluation": response_text, "score": 5.0, "suggestions": ""}

        score = float(evaluation_data.get("score", 5.0))
        route = "pass" if score >= pass_threshold else "revise"

        output_dir = PersistenceHelper.make_output_dir("experiment_results", "goal_eval")
        eval_path = output_dir / "goal_evaluation.json"
        PersistenceHelper.write_json(eval_path, evaluation_data)

        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir,
            {"goal_evaluation": str(eval_path)},
        )

        logger.info(
            "ExperimentGoalEvaluator: score=%.2f, route=%s", score, route,
        )

        return {
            "evaluation": evaluation_data.get("evaluation", ""),
            "suggestions": evaluation_data.get("suggestions", ""),
            "_route": route,
            "_score": score,
            "persistence_info": persistence_info,
        }
