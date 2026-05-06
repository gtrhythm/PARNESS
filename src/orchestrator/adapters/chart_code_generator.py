import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from .base import LLMAgentModule

logger = logging.getLogger(__name__)


class ChartCodeGeneratorModule(LLMAgentModule):
    module_name = "chart_code_generator"

    INPUT_SPEC = {
        "experiment_results": {"type": "dict", "required": False, "default": {}},
        "experiment_plan": {"type": "str", "required": False, "default": ""},
        "chart_requirements": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "chart_paths": {"type": "list"},
        "chart_code": {"type": "str"},
        "persistence_info": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.experiment_agents.persistence import PersistenceHelper

        experiment_results = inputs.get("experiment_results", {})
        experiment_plan = inputs.get("experiment_plan", "")
        chart_requirements = inputs.get("chart_requirements", "")

        execution_mode = self.config.get("execution_mode", "direct")
        output_formats = self.config.get("output_formats", ["png"])
        max_retries = self.config.get("max_retries", 2)

        requirements_section = ""
        if chart_requirements:
            requirements_section = f"\n\nSpecific chart requirements:\n{chart_requirements}"

        plan_section = ""
        if experiment_plan:
            plan_section = f"\n\nExperiment plan context:\n{experiment_plan}"

        prompt = (
            "You are an expert data visualization engineer. Generate Python matplotlib code "
            "to create charts from the experiment results.\n\n"
            f"Experiment results:\n{json.dumps(experiment_results, ensure_ascii=False, indent=2)}"
            f"{plan_section}"
            f"{requirements_section}\n\n"
            "Requirements:\n"
            "- Generate complete, runnable Python code using matplotlib\n"
            "- Save charts using plt.savefig() to the current directory\n"
            "- Use filenames like 'chart_0.png', 'chart_1.png', etc.\n"
            f"- Save in these formats: {output_formats}\n"
            "- Return ONLY the Python code, no explanation or markdown fences"
        )

        llm_client = self._get_llm_client()
        response = await llm_client.chat(prompt)
        chart_code = response if isinstance(response, str) else str(response)

        chart_code = chart_code.strip()
        if chart_code.startswith("```python"):
            chart_code = chart_code[len("```python"):]
        if chart_code.startswith("```"):
            chart_code = chart_code[len("```"):]
        if chart_code.endswith("```"):
            chart_code = chart_code[:-len("```")]
        chart_code = chart_code.strip()

        output_dir = PersistenceHelper.make_output_dir("experiment_charts", "charts")
        code_path = output_dir / "chart_code.py"
        PersistenceHelper.write_text(code_path, chart_code)

        chart_paths: List[str] = []

        if execution_mode == "direct":
            for attempt in range(max_retries + 1):
                try:
                    proc = subprocess.run(
                        [sys.executable, str(code_path)],
                        capture_output=True,
                        text=True,
                        timeout=120,
                        cwd=str(output_dir),
                    )
                    if proc.returncode == 0:
                        break
                    elif attempt < max_retries:
                        fix_prompt = (
                            f"The following chart code failed with error:\n{proc.stderr}\n\n"
                            f"Original code:\n{chart_code}\n\n"
                            "Fix the code and return ONLY the corrected Python code."
                        )
                        response = await llm_client.chat(fix_prompt)
                        chart_code = response if isinstance(response, str) else str(response)
                        chart_code = chart_code.strip()
                        if chart_code.startswith("```python"):
                            chart_code = chart_code[len("```python"):]
                        if chart_code.startswith("```"):
                            chart_code = chart_code[len("```"):]
                        if chart_code.endswith("```"):
                            chart_code = chart_code[:-len("```")]
                        chart_code = chart_code.strip()
                        PersistenceHelper.write_text(code_path, chart_code)
                    else:
                        logger.warning(
                            "ChartCodeGenerator: code failed after %d retries: %s",
                            max_retries, proc.stderr[:200],
                        )
                except subprocess.TimeoutExpired:
                    logger.warning("ChartCodeGenerator: code execution timed out")
                except Exception as e:
                    logger.warning("ChartCodeGenerator: execution error: %s", e)

            for ext in output_formats:
                for p in sorted(output_dir.glob(f"chart_*.{ext}")):
                    chart_paths.append(str(p))

        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir,
            {"chart_code": str(code_path), "charts": chart_paths},
        )

        logger.info(
            "ChartCodeGenerator: mode=%s, %d charts generated",
            execution_mode, len(chart_paths),
        )

        return {
            "chart_paths": chart_paths,
            "chart_code": chart_code,
            "persistence_info": persistence_info,
        }
