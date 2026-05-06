import json
import logging
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class ExperimentExecutorOpencodeModule(BaseModule):
    module_name = "experiment_executor_opencode"

    INPUT_SPEC = {
        "experiment_plan": {"type": "str", "required": False, "default": ""},
        "resource_context": {"type": "dict", "required": False, "default": {}},
    }
    OUTPUT_SPEC = {
        "experiment_results": {"type": "dict"},
        "execution_log": {"type": "str"},
        "workdir": {"type": "str"},
        "session_id": {"type": "str"},
        "persistence_info": {"type": "dict"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.experiment_agents.opencode_client import OpenCodeClient
        from src.experiment_agents.persistence import PersistenceHelper

        experiment_plan = inputs.get("experiment_plan", "")
        resource_context = inputs.get("resource_context", {})

        opencode_config = self.config.get("opencode", {})
        client = OpenCodeClient(config=opencode_config)

        await client.ensure_server()
        workdir = await client.create_workspace(prefix="exp_exec")

        timeout = self.config.get("timeout", 3600)
        model = self.config.get("model", "")

        prompt = (
            "Execute the following experiment plan. Implement all code, run the experiments, "
            "and save all results to files in the current directory.\n\n"
            f"Experiment plan:\n{experiment_plan}\n\n"
            "Save results as 'results.json' and any logs as 'execution.log'."
        )

        if resource_context:
            prompt += f"\n\nResource context: {json.dumps(resource_context, ensure_ascii=False)}"

        result = await client.run(
            prompt=prompt,
            workdir=workdir,
            model=model,
            timeout=timeout,
        )

        output_dir = PersistenceHelper.make_output_dir("experiment_results", "execution")
        execution_result = {
            "session_id": result.session_id,
            "success": result.success,
            "text": result.text,
            "tool_calls": result.tool_calls,
            "total_tokens": result.total_tokens,
            "error": result.error,
            "workdir": workdir,
        }

        results_path = output_dir / "execution_result.json"
        PersistenceHelper.write_json(results_path, execution_result)

        log_path = output_dir / "execution.log"
        log_text = result.text if result.success else f"ERROR: {result.error}\n\n{result.text}"
        PersistenceHelper.write_text(log_path, log_text)

        from pathlib import Path
        workspace_results_path = Path(workdir) / "results.json"
        experiment_results = {}
        if workspace_results_path.exists():
            with open(workspace_results_path, "r", encoding="utf-8") as f:
                experiment_results = json.load(f)

        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir,
            {
                "execution_result": str(results_path),
                "execution_log": str(log_path),
                "workspace": workdir,
            },
            session_id=result.session_id,
        )

        logger.info(
            "ExperimentExecutorOpencode: success=%s, session=%s, workdir=%s",
            result.success, result.session_id, workdir,
        )

        return {
            "experiment_results": experiment_results,
            "execution_log": log_text,
            "workdir": workdir,
            "session_id": result.session_id,
            "persistence_info": persistence_info,
        }
