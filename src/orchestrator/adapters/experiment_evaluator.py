import json
import logging
from pathlib import Path
from typing import Any, Dict

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class ExperimentEvaluatorModule(LLMAgentModule):
    module_name = "experiment_evaluator"

    INPUT_SPEC = {
        "experiment_results": {"type": "list", "required": False, "default": []},
        "task_type": {"type": "str", "required": False, "default": "classification"},
        "evaluation_metrics": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "evaluation_metrics": {"type": "dict"},
        "evaluation_report": {"type": "str"},
        "comparison_with_baseline": {"type": "dict"},
        "visualizations": {"type": "list"},
        "summary": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.evaluator.evaluator import Evaluator, EvalConfig, TrainResult
        from src.experiment_runner.models import ExperimentResult, ExecutionStatus

        raw_results = inputs.get("experiment_results", [])
        if not raw_results:
            return {
                "evaluation_metrics": {},
                "evaluation_report": "No experiment results to evaluate",
                "comparison_with_baseline": {},
                "summary": "No results provided",
            }

        best = self._pick_best(raw_results)
        if best is None:
            return {
                "evaluation_metrics": {},
                "evaluation_report": "All experiments failed",
                "comparison_with_baseline": {},
                "summary": "No successful experiments",
            }

        task_type = inputs.get("task_type", self.config.get("task_type", "classification"))
        metrics_list = inputs.get("evaluation_metrics", self.config.get("metrics", []))

        output_dir = self.config.get("output_dir", "output/eval")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        eval_config = EvalConfig(
            output_dir=output_dir,
            task_type=task_type,
            metrics=metrics_list,
            generate_visualizations=self.config.get("generate_visualizations", True),
            generate_report=self.config.get("generate_report", True),
            report_format=self.config.get("report_format", "markdown"),
            baseline_path=self.config.get("baseline_path"),
        )

        evaluator = Evaluator(eval_config)

        train_result = TrainResult(
            idea_id=best.get("idea_id", ""),
            predictions=best.get("predictions", []),
            labels=best.get("labels", []),
            metadata={
                "workdir": best.get("workdir", ""),
                "duration_seconds": best.get("duration_seconds", 0),
                "retry_count": best.get("retry_count", 0),
            },
        )

        eval_result = await evaluator.evaluate(train_result)

        all_metrics = {**best.get("metrics", {}), **eval_result.metrics}

        return {
            "evaluation_metrics": all_metrics,
            "evaluation_report": eval_result.report,
            "comparison_with_baseline": eval_result.comparison_with_baseline,
            "visualizations": eval_result.visualizations,
            "summary": self._summarize(all_metrics, eval_result.comparison_with_baseline),
            "_task_type": task_type,
        }

    def emit_output(self, result):
        if not result.get("evaluation_metrics"):
            return None
        return AgentOutput(
            display_type="table",
            title="Experiment Evaluation",
            data={"evaluation_metrics": result.get("evaluation_metrics", {}),
                  "comparison_with_baseline": result.get("comparison_with_baseline", {}),
                  "task_type": result.get("_task_type", "classification")},
            render_hints={"columns": ["Metric", "Value", "Baseline", "Difference", "Improved?"],
                          "highlight_improvements": True},
        )

    def _pick_best(self, results: list) -> Dict[str, Any] | None:
        best = None
        best_acc = -1.0
        for r in results:
            if isinstance(r, dict):
                status = r.get("status", "failed")
            else:
                status = getattr(r, "status", "failed")
                if hasattr(status, "value"):
                    status = status.value

            if status != "success":
                continue

            metrics = r.get("metrics", {}) if isinstance(r, dict) else getattr(r, "metrics", {})
            acc = metrics.get("accuracy", metrics.get("f1", 0))
            if acc > best_acc:
                best_acc = acc
                best = r if isinstance(r, dict) else r.to_dict()

        return best

    def _summarize(self, metrics: Dict[str, float], comparison: Dict) -> str:
        parts = ["Evaluation complete."]
        if metrics:
            top = list(metrics.items())[:5]
            parts.append("Top metrics: " + ", ".join(f"{k}={v:.4f}" if isinstance(v, (int, float)) else f"{k}={v}" for k, v in top))
        if comparison:
            improved = sum(
                1 for v in comparison.values()
                if isinstance(v, dict) and v.get("difference", 0) > 0
            )
            parts.append(f"Improved over baseline: {improved}/{len(comparison)} metrics")
        return " ".join(parts)
