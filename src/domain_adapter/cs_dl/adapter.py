from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from ..base import DomainAdapter
from ..models import (
    CorrectionPlan,
    ExperimentFeedback,
    ExperimentPlan,
    ResourceSpec,
    TaskClassification,
    ToolSpec,
    TuningSuggestion,
    ValidationResult,
)
from .gpu_bridge import GPUBridge
from .auto_tuner import AutoTuner

logger = logging.getLogger(__name__)

_CS_DESIGN_PROMPT = """You are an ML experiment designer. Design an experiment for the following idea.

## Research Idea
Title: {title}
Description: {description}
Category: {category}
Methodology: {methodology}

## Available Resources
{resources}

## Your Task
Design a concrete experiment plan including:
1. Dataset selection (with URL if public)
2. Baseline method to compare against
3. Hyperparameters (learning rate, batch size, epochs, etc.)
4. Evaluation metrics
5. Code outline for implementation

Return JSON:
{{
  "dataset": "<name>",
  "dataset_url": "<url>",
  "baseline": "<method name>",
  "baseline_paper": "<citation>",
  "hyperparameters": {{
    "learning_rate": <value>,
    "batch_size": <value>,
    "epochs": <value>,
    "optimizer": "<name>",
    "weight_decay": <value>
  }},
  "evaluation_metrics": ["<metric1>", "<metric2>"],
  "experimental_setup": {{
    "train_test_split": "<ratio>",
    "cross_validation": <folds>,
    "data_augmentation": "<description>",
    "hardware": "<description>"
  }},
  "expected_results": "<description>",
  "code_outline": "<pseudocode or description>"
}}
"""


class CSDLAdapter(DomainAdapter):
    """Domain adapter for Computer Science / Deep Learning research.

    Integrates with local GPU resources, provides auto-tuning,
    and leverages the existing experiment_runner infrastructure.
    """

    def __init__(self, llm_client=None, resource_bridge=None,
                 gpu_bridge: Optional[GPUBridge] = None,
                 auto_tuner: Optional[AutoTuner] = None):
        super().__init__(llm_client=llm_client, resource_bridge=resource_bridge)
        self.gpu_bridge = gpu_bridge or GPUBridge(resource_bridge)
        self.auto_tuner = auto_tuner or AutoTuner(llm_client)

    def domain_name(self) -> str:
        return "cs_dl"

    def experiment_paradigm(self) -> str:
        return "code_execution"

    def required_tools(self) -> List[ToolSpec]:
        tools = [
            ToolSpec(name="python", version="3.10+", required=True,
                     check_command="python --version"),
        ]

        try:
            import torch
            tools.append(ToolSpec(name="pytorch", version=torch.__version__,
                                  required=False, check_command="python -c 'import torch'"))
        except ImportError:
            tools.append(ToolSpec(name="pytorch", required=False,
                                  install_command="pip install torch"))

        return tools

    def resource_requirements(self) -> ResourceSpec:
        gpus = self.gpu_bridge.detect_gpus()
        gpu_count = len(gpus)
        gpu_mem = max((g.get("memory_total_mb", 0) for g in gpus), default=0) // 1024

        return ResourceSpec(
            gpu_required=gpu_count > 0,
            gpu_count=max(1, gpu_count),
            gpu_memory_gb=gpu_mem,
            cpu_cores=4,
            ram_gb=16,
            disk_gb=50,
            estimated_duration_hours=4.0,
        )

    async def design_experiment(
        self,
        idea: Any,
        resources: Optional[ResourceSpec] = None,
    ) -> ExperimentPlan:
        idea_id = getattr(idea, "idea_id", "") or hashlib.sha256(
            getattr(idea, "title", "").encode()
        ).hexdigest()[:16]

        res_spec = resources or self.resource_requirements()
        resources_str = json.dumps(res_spec.to_dict(), indent=2)

        if self.llm is None:
            return self._default_plan(idea, idea_id, res_spec)

        try:
            from src.idea_agents.llm_utils import call_llm, parse_json_response

            prompt = _CS_DESIGN_PROMPT.format(
                title=getattr(idea, "title", ""),
                description=getattr(idea, "description", "")[:1500],
                category=getattr(idea, "category", ""),
                methodology=getattr(idea, "methodology", ""),
                resources=resources_str,
            )

            resp = await call_llm(self.llm, prompt)
            data = parse_json_response(resp)

            hp = data.get("hyperparameters", {})
            if res_spec.gpu_required and "batch_size" not in hp:
                hp["batch_size"] = self.gpu_bridge.suggest_batch_size(
                    model_params_m=100,
                    precision="fp32",
                )

            return ExperimentPlan(
                plan_id=f"cs_dl_{idea_id}_{int(time.time())}",
                domain="cs_dl",
                paradigm="code_execution",
                idea_id=idea_id,
                idea_title=getattr(idea, "title", ""),
                description=data.get("expected_results", ""),
                steps=self._build_steps(data),
                parameters=hp,
                expected_outputs=data.get("evaluation_metrics", []),
                success_criteria={
                    "metrics": data.get("evaluation_metrics", []),
                    "minimum_improvement": "1% over baseline",
                },
                resource_requirements=res_spec,
                dataset=data.get("dataset", ""),
                baseline=data.get("baseline", ""),
                evaluation_metrics=data.get("evaluation_metrics", []),
                code=data.get("code_outline", ""),
            )
        except Exception as e:
            logger.warning("LLM experiment design failed: %s", e)
            return self._default_plan(idea, idea_id, res_spec)

    async def run_experiment(
        self,
        plan: ExperimentPlan,
        resources: Optional[ResourceSpec] = None,
    ) -> ExperimentFeedback:
        from src.experiment_runner.models import EnvironmentSpec, ExperimentSpec
        from src.experiment_runner.executor import OpenCodeExecutor

        gpu_idx = None
        if plan.resource_requirements and plan.resource_requirements.gpu_required:
            gpu_idx = self.gpu_bridge.allocate_gpu(
                plan.resource_requirements.gpu_memory_gb * 1024
            )

        env = EnvironmentSpec(
            gpu_count=plan.resource_requirements.gpu_count if plan.resource_requirements else 0,
            gpu_type=f"cuda:{gpu_idx}" if gpu_idx is not None else "",
            extra_packages=["torch", "numpy", "scikit-learn"],
        )

        spec = ExperimentSpec(
            idea_id=plan.idea_id,
            idea_title=plan.idea_title,
            idea_description=plan.description,
            dataset=plan.dataset,
            dataset_url=plan.parameters.get("dataset_url", ""),
            baseline=plan.baseline,
            baseline_paper=plan.parameters.get("baseline_paper", ""),
            hyperparameters=plan.parameters,
            evaluation_metrics=plan.evaluation_metrics,
            experimental_setup={
                "code_outline": plan.code,
                "steps": plan.steps,
            },
            environment=env,
            timeout_seconds=3600,
            max_retries=2,
        )

        executor = OpenCodeExecutor(
            default_timeout=3600,
            max_retries=2,
            llm_client=self.llm,
        )

        result = await executor.execute(spec)

        return ExperimentFeedback(
            idea_id=plan.idea_id,
            status=result.status.value,
            metrics=result.metrics,
            errors=[result.error_message] if result.error_message else [],
            stdout=result.stdout,
            stderr=result.stderr,
            artifacts=result.artifacts,
        )

    async def validate_result(
        self,
        feedback: ExperimentFeedback,
        plan: ExperimentPlan,
    ) -> ValidationResult:
        issues = []
        score = 5.0

        if feedback.status != "success":
            issues.append({
                "severity": "critical",
                "category": "execution",
                "message": f"Experiment failed: {feedback.status}",
            })
            return ValidationResult(is_valid=False, score=0.0, issues=issues)

        metrics = feedback.metrics
        if not metrics:
            issues.append({
                "severity": "critical",
                "category": "completeness",
                "message": "No metrics collected",
            })
            return ValidationResult(is_valid=False, score=0.0, issues=issues)

        for metric_name in plan.evaluation_metrics:
            if metric_name not in metrics:
                issues.append({
                    "severity": "warning",
                    "category": "completeness",
                    "message": f"Missing metric: {metric_name}",
                })

        acc = metrics.get("accuracy", 0)
        f1 = metrics.get("f1", 0)
        loss = metrics.get("loss", float("inf"))

        if acc > 0 or f1 > 0:
            performance = max(acc, f1)
            if performance >= 0.9:
                score = 9.0
            elif performance >= 0.8:
                score = 7.5
            elif performance >= 0.7:
                score = 6.0
            elif performance >= 0.5:
                score = 4.0
            else:
                score = 2.0
                issues.append({
                    "severity": "warning",
                    "category": "performance",
                    "message": f"Low performance: {performance:.3f}",
                })

        if loss > 0 and loss < 0.01:
            issues.append({
                "severity": "warning",
                "category": "red_flag",
                "message": "Suspiciously low loss, possible overfitting or data leakage",
            })

        is_valid = score >= 6.0 and not any(
            i["severity"] == "critical" for i in issues
        )

        return ValidationResult(
            is_valid=is_valid,
            score=score,
            issues=issues,
            numerical_accuracy=metrics,
        )

    async def auto_correct(
        self,
        feedback: ExperimentFeedback,
        validation: ValidationResult,
        plan: ExperimentPlan,
    ) -> CorrectionPlan:
        fix_hints = []
        modified_params = dict(plan.parameters)

        for issue in validation.issues:
            cat = issue.get("category", "")
            msg = issue.get("message", "")

            if cat == "execution":
                fix_hints.append(f"Fix execution error: {msg}")
                if feedback.stderr:
                    fix_hints.append(f"Stderr hint: {feedback.stderr[:500]}")

            elif cat == "completeness":
                fix_hints.append(f"Ensure all metrics are computed: {msg}")

            elif cat == "red_flag" and "leakage" in msg.lower():
                fix_hints.append("Check train/test split for data leakage")
                fix_hints.append("Verify no target information leaks into features")

            elif cat == "performance":
                fix_hints.append("Try: increase model capacity, reduce regularization, longer training")

        if feedback.status == "success" and validation.score < 6.0:
            lr = modified_params.get("learning_rate", modified_params.get("lr", 0.001))
            modified_params["learning_rate"] = lr * 0.5
            modified_params["epochs"] = modified_params.get("epochs", 10) * 2
            fix_hints.append("Reduced learning rate and doubled epochs for better convergence")

        return CorrectionPlan(
            correction_type="parameter_adjustment",
            description=f"Auto-correction based on {len(validation.issues)} issues",
            modified_parameters=modified_params,
            fix_hints=fix_hints,
            estimated_improvement="Expected 5-15% improvement with adjusted parameters",
        )

    async def auto_tune(
        self,
        history: List[ExperimentFeedback],
        validation: ValidationResult,
    ) -> List[TuningSuggestion]:
        if not history:
            return []

        latest = history[-1]
        params = {
            "learning_rate": 0.001,
            "batch_size": 32,
            "epochs": 10,
        }

        suggestions = await self.auto_tuner.suggest(
            history=[h.to_dict() for h in history],
            current_metrics=latest.metrics,
            current_params=params,
            status=latest.status,
        )

        return [
            TuningSuggestion(
                parameter_name=s.get("parameter_name", ""),
                current_value=s.get("current_value"),
                suggested_value=s.get("suggested_value"),
                reason=s.get("reason", ""),
                confidence=s.get("confidence", 0.0),
                priority=s.get("priority", 3),
            )
            for s in suggestions
        ]

    def classify_tasks(self, idea: Any) -> TaskClassification:
        from ..task_classifier import HumanMachineTaskClassifier
        classifier = HumanMachineTaskClassifier(self.llm)
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return classifier._rule_based_classify(idea, "cs_dl")
            return loop.run_until_complete(classifier.classify(idea, "cs_dl"))
        except RuntimeError:
            return classifier._rule_based_classify(idea, "cs_dl")

    def _build_steps(self, data: dict) -> List[Dict[str, Any]]:
        return [
            {"step": 1, "action": "Download and prepare dataset",
             "details": data.get("dataset", "")},
            {"step": 2, "action": "Implement baseline method",
             "details": data.get("baseline", "")},
            {"step": 3, "action": "Implement proposed method",
             "details": data.get("code_outline", "")},
            {"step": 4, "action": "Train both models",
             "details": data.get("hyperparameters", {})},
            {"step": 5, "action": "Evaluate and compare",
             "details": data.get("evaluation_metrics", [])},
        ]

    def _default_plan(self, idea: Any, idea_id: str,
                      res_spec: ResourceSpec) -> ExperimentPlan:
        return ExperimentPlan(
            plan_id=f"cs_dl_{idea_id}_{int(time.time())}",
            domain="cs_dl",
            paradigm="code_execution",
            idea_id=idea_id,
            idea_title=getattr(idea, "title", ""),
            description=getattr(idea, "description", "")[:500],
            steps=[],
            parameters={
                "learning_rate": 0.001,
                "batch_size": self.gpu_bridge.suggest_batch_size(100),
                "epochs": 50,
                "optimizer": "adam",
            },
            expected_outputs=["accuracy", "loss"],
            success_criteria={"minimum_accuracy": 0.7},
            resource_requirements=res_spec,
            dataset="auto_select",
            baseline="auto_select",
            evaluation_metrics=["accuracy", "loss", "f1"],
        )
