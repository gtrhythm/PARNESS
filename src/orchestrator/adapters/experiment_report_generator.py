import logging
from typing import Any, Dict

from .base import LLMAgentModule

logger = logging.getLogger(__name__)


class ExperimentReportGeneratorModule(LLMAgentModule):
    module_name = "experiment_report_generator"

    INPUT_SPEC = {
        "idea": {"type": "str", "required": False, "default": ""},
        "experiment_plan": {"type": "str", "required": False, "default": ""},
        "experiment_results": {"type": "any", "required": False, "default": {}},
        "goal_evaluation": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "report": {"type": "str"},
        "report_path": {"type": "str"},
        "persistence_info": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        import json
        from src.experiment_agents.persistence import PersistenceHelper

        idea = inputs.get("idea", "")
        experiment_plan = inputs.get("experiment_plan", "")
        experiment_results = inputs.get("experiment_results", {})
        goal_evaluation = inputs.get("goal_evaluation", "")

        goal_section = ""
        if goal_evaluation:
            goal_section = f"\n\nGoal evaluation:\n{goal_evaluation}"

        prompt = (
            "You are an expert scientific report writer. Generate a comprehensive markdown "
            "experiment report.\n\n"
            f"Original idea:\n{idea}\n\n"
            f"Experiment plan:\n{experiment_plan}\n\n"
            f"Experiment results:\n{json.dumps(experiment_results, ensure_ascii=False, indent=2)}"
            f"{goal_section}\n\n"
            "Generate a markdown report with these sections: "
            "# Title, ## Abstract, ## Introduction, ## Methodology, "
            "## Results, ## Discussion, ## Conclusion. "
            "Return the report as a plain markdown string, NOT JSON."
        )

        llm_client = self._get_llm_client()
        response = await llm_client.chat(prompt)
        report = response if isinstance(response, str) else str(response)

        output_dir = PersistenceHelper.make_output_dir("experiment_reports", "report")
        report_path = output_dir / "experiment_report.md"
        PersistenceHelper.write_text(report_path, report)

        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir,
            {"report": str(report_path)},
        )

        logger.info("ExperimentReportGenerator: report at %s", report_path)

        return {
            "report": report,
            "report_path": str(report_path),
            "persistence_info": persistence_info,
        }
