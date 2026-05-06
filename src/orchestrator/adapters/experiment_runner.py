from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class ExperimentRunnerModule(LLMAgentModule):
    module_name = "experiment_runner"

    INPUT_SPEC = {
        "designed_experiments": {"type": "list", "required": False, "default": []},
        "idea_id": {"type": "str", "required": False, "default": ""},
        "idea_title": {"type": "str", "required": False, "default": ""},
        "idea_description": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "experiment_results": {"type": "list"},
        "execution_metrics": {"type": "dict"},
        "best_result": {"type": "dict"},
        "summary": {"type": "str"},
        "success_count": {"type": "int"},
        "fail_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.experiment_runner.iterative_loop import IterativeExperimentLoop
        from src.experiment_runner.executor import OpenCodeExecutor
        from src.experiment_runner.agents import (
            ExperimentDirectorAgent,
            ExperimentReviewAgent,
        )
        from src.experiment_runner.models import (
            EnvironmentSpec,
            EnvironmentType,
            ExperimentSpec,
        )

        designs = inputs.get("designed_experiments", [])
        if isinstance(designs, dict):
            designs = [designs]

        idea_id = inputs.get("idea_id", "")
        idea_title = inputs.get("idea_title", "")
        idea_description = inputs.get("idea_description", "")

        if not designs:
            return {
                "experiment_results": [],
                "execution_metrics": {},
                "summary": "No experiment designs provided",
                "error": "no_designs",
            }

        llm_client = self.config.get("llm_client")
        if not llm_client:
            return {
                "experiment_results": [],
                "execution_metrics": {},
                "summary": "No LLM client configured for agents",
                "error": "no_llm_client",
            }

        max_rounds = self.config.get("max_rounds", 4)

        env_spec = self._build_env_spec(self.config.get("environment", {}))
        executor = self._create_executor(env_spec)
        reviewer = ExperimentReviewAgent(llm_client)
        score_threshold = self.config.get("score_threshold", 6.5)
        director = ExperimentDirectorAgent(
            llm_client,
            max_rounds=max_rounds,
            score_threshold=score_threshold,
        )

        loop = IterativeExperimentLoop(
            executor=executor,
            reviewer=reviewer,
            director=director,
            max_rounds=max_rounds,
            score_threshold=score_threshold,
            evaluator_config=self.config.get("evaluator", {}),
        )

        specs = self._build_specs(designs, idea_id, idea_title, idea_description, env_spec)

        max_concurrent = self.config.get("max_concurrent", 1)
        if len(specs) == 1:
            results = [await loop.run(specs[0])]
        else:
            results = await loop.run_batch(specs, max_concurrent=max_concurrent)

        return self._aggregate(results)

    def emit_output(self, result):
        if result.get("error"):
            return None
        accepted_count = result.get("success_count", 0)
        fail_count = result.get("fail_count", 0)
        color = "green" if accepted_count > 0 else "orange"
        return AgentOutput(
            display_type="metrics",
            title="Experiment Results",
            content=f"{accepted_count} accepted, {fail_count} not accepted",
            data={"success_count": accepted_count, "fail_count": fail_count,
                  "best_metrics": result.get("execution_metrics", {})},
            render_hints={"color": color},
        )

    def _build_specs(
        self,
        designs: List[Dict],
        idea_id: str,
        idea_title: str,
        idea_description: str,
        env_spec: EnvironmentSpec,
    ) -> List[ExperimentSpec]:
        from src.experiment_runner.models import ExperimentSpec

        specs = []
        for i, design in enumerate(designs):
            spec = ExperimentSpec(
                idea_id=idea_id or design.get("idea_id", f"exp_{i}"),
                idea_title=idea_title or design.get("idea_title", ""),
                idea_description=idea_description or design.get("idea_description", ""),
                dataset=design.get("dataset", ""),
                dataset_url=design.get("dataset_url", ""),
                baseline=design.get("baseline", ""),
                baseline_paper=design.get("baseline_paper", ""),
                hyperparameters=design.get("hyperparameters", {}),
                evaluation_metrics=design.get("evaluation_metrics", []),
                experimental_setup=design.get("experimental_setup", {}),
                expected_results=design.get("expected_results", ""),
                environment=env_spec,
                timeout_seconds=self.config.get("timeout_seconds", 3600),
                max_retries=self.config.get("max_retries", 3),
                workdir=str(
                    Path(self.config.get("workdir_base", "output/experiments"))
                    / f"{idea_id or 'exp'}_v{i}"
                ),
            )
            specs.append(spec)
        return specs

    def _build_env_spec(self, env_cfg: Dict[str, Any]) -> EnvironmentSpec:
        from src.experiment_runner.models import EnvironmentSpec, EnvironmentType

        env_type_str = env_cfg.get("env_type", "local")
        try:
            env_type = EnvironmentType(env_type_str)
        except ValueError:
            env_type = EnvironmentType.LOCAL

        return EnvironmentSpec(
            python_version=env_cfg.get("python_version", "3.10"),
            gpu_count=env_cfg.get("gpu_count", 0),
            gpu_type=env_cfg.get("gpu_type", ""),
            extra_packages=env_cfg.get("extra_packages", []),
            docker_image=env_cfg.get("docker_image", ""),
            env_type=env_type,
            env_vars=env_cfg.get("env_vars", {}),
        )

    def _create_executor(self, env_spec: EnvironmentSpec):
        from src.experiment_runner.executor import OpenCodeExecutor, SandboxExecutor
        from src.experiment_runner.models import EnvironmentType

        common_kwargs = {
            "opencode_bin": self.config.get("opencode_bin", "opencode"),
            "default_timeout": self.config.get("timeout_seconds", 3600),
            "max_retries": self.config.get("max_retries", 3),
            "workdir_base": self.config.get("workdir_base", "output/experiments"),
        }

        if env_spec.env_type == EnvironmentType.CONDA:
            return SandboxExecutor(**common_kwargs)

        return OpenCodeExecutor(**common_kwargs)

    def _aggregate(self, results: List) -> Dict[str, Any]:
        serialized = [r.to_dict() for r in results]

        accepted = [r for r in results if r.accepted]
        not_accepted = [r for r in results if not r.accepted]

        best = None
        best_metrics: Dict[str, float] = {}
        for r in results:
            if r.final_metrics:
                score = r.final_metrics.get("accuracy", r.final_metrics.get("f1", 0))
                best_score = best_metrics.get("accuracy", best_metrics.get("f1", 0))
                if not best or score > best_score:
                    best = r
                    best_metrics = r.final_metrics

        summary_parts = [
            f"Total experiments: {len(results)}",
            f"Accepted by director: {len(accepted)}",
            f"Not accepted (best-effort): {len(not_accepted)}",
        ]
        for r in results:
            summary_parts.append(
                f"  {r.idea_id}: {r.total_rounds} rounds, "
                f"accepted={r.accepted}, "
                f"final_metrics={json.dumps(r.final_metrics) if r.final_metrics else 'N/A'}"
            )

        return {
            "experiment_results": serialized,
            "execution_metrics": best_metrics,
            "best_result": best.to_dict() if best else None,
            "summary": "\n".join(summary_parts),
            "success_count": len(accepted),
            "fail_count": len(not_accepted),
        }
