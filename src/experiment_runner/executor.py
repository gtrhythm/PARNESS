import asyncio
import json
import logging
import shutil
import tempfile
import time
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import EnvironmentSpec, ExperimentResult, ExperimentSpec, ExecutionStatus

logger = logging.getLogger(__name__)


class OpenCodeExecutor:
    """Execute experiments by invoking opencode in headless mode.

    opencode is invoked via ``opencode run --prompt <prompt> --workdir <dir>``.
    The executor constructs a prompt from the ExperimentSpec, lets opencode
    generate and run the code, then collects results from the workdir.
    """

    def __init__(
        self,
        opencode_bin: str = "opencode",
        default_timeout: int = 3600,
        max_retries: int = 3,
        workdir_base: str = "",
        llm_client=None,
    ):
        self.opencode_bin = opencode_bin
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self.workdir_base = workdir_base or tempfile.mkdtemp(prefix="opencode_exp_")
        self.llm_client = llm_client

    def _build_prompt(self, spec: ExperimentSpec) -> str:
        hp_str = json.dumps(spec.hyperparameters, indent=2)
        metrics_str = ", ".join(spec.evaluation_metrics)
        setup_str = json.dumps(spec.experimental_setup, indent=2)

        prompt = f"""You are an ML research engineer. Implement and run the following experiment end-to-end.

## Research Idea
Title: {spec.idea_title}
Description: {spec.idea_description}

## Experiment Configuration
- Dataset: {spec.dataset}
- Dataset URL: {spec.dataset_url}
- Baseline method: {spec.baseline} (from: {spec.baseline_paper})
- Evaluation metrics: {metrics_str}
- Hyperparameters:
{hp_str}
- Additional setup:
{setup_str}

## Your Task
1. Download the dataset from the URL (if needed, use wget/curl or huggingface datasets).
2. Implement the **baseline method** as described in the paper.
3. Implement the **proposed method** based on the idea description.
4. Train both models with the given hyperparameters.
5. Evaluate both models on the test set using the specified metrics.
6. Write the final results to a file called `results.json` in the current directory.

## results.json format (YOU MUST create this file)
{{
  "idea_id": "{spec.idea_id}",
  "status": "success",
  "metrics": {{
    "<metric_name>": <value>,
    ...
  }},
  "baseline_metrics": {{
    "<metric_name>": <value>,
    ...
  }},
  "predictions": [<list of predicted labels/values>],
  "labels": [<list of ground truth labels/values>],
  "summary": "<1-2 sentence summary of results>"
}}

IMPORTANT:
- If the dataset is too large, use a small subset for a quick smoke test.
- If something fails, debug and fix the issue. Do NOT give up.
- The `results.json` file MUST exist when you are done.
- Keep the code clean and well-organized.
- Print progress to stdout so we can track execution.
"""
        return prompt

    def _prepare_workdir(self, spec: ExperimentSpec) -> Path:
        if spec.workdir:
            workdir = Path(spec.workdir)
        else:
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in spec.idea_id)
            workdir = Path(self.workdir_base) / f"exp_{safe_name}"

        workdir.mkdir(parents=True, exist_ok=True)

        env = spec.environment
        if env.extra_packages:
            req_path = workdir / "requirements.txt"
            if not req_path.exists():
                req_path.write_text("\n".join(env.extra_packages) + "\n")

        return workdir

    async def _run_opencode(
        self,
        prompt: str,
        workdir: Path,
        timeout: int,
    ) -> Dict[str, Any]:
        prompt_file = workdir / "_prompt.txt"
        prompt_file.write_text(prompt, encoding="utf-8")

        cmd = [
            self.opencode_bin,
            "run",
            "--prompt", prompt,
            "--workdir", str(workdir),
        ]

        env = os.environ.copy()
        env["OPENCODE_NONINTERACTIVE"] = "1"

        logger.info("Launching opencode in %s (timeout=%ds)", workdir, timeout)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workdir),
            env=env,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            return_code = proc.returncode
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            stdout = ""
            stderr = "Process timed out"
            return_code = -1

        return {
            "return_code": return_code,
            "stdout": stdout,
            "stderr": stderr,
        }

    def _collect_results(self, workdir: Path, proc_result: Dict[str, Any]) -> ExperimentResult:
        results_json = workdir / "results.json"
        if results_json.exists():
            try:
                data = json.loads(results_json.read_text(encoding="utf-8"))
                return ExperimentResult(
                    idea_id=data.get("idea_id", ""),
                    status=ExecutionStatus.SUCCESS,
                    predictions=data.get("predictions", []),
                    labels=data.get("labels", []),
                    metrics=data.get("metrics", {}),
                    raw_output=proc_result.get("stdout", ""),
                    workdir=str(workdir),
                    stdout=proc_result.get("stdout", ""),
                    stderr=proc_result.get("stderr", ""),
                    artifacts={"results_json": str(results_json)},
                )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to parse results.json: %s", e)

        metrics = self._extract_metrics_from_output(proc_result.get("stdout", ""))
        status = ExecutionStatus.SUCCESS if proc_result.get("return_code") == 0 and metrics else ExecutionStatus.FAILED

        return ExperimentResult(
            idea_id="",
            status=status,
            metrics=metrics,
            raw_output=proc_result.get("stdout", ""),
            error_message=proc_result.get("stderr", "")[:2000],
            workdir=str(workdir),
            stdout=proc_result.get("stdout", ""),
            stderr=proc_result.get("stderr", ""),
            artifacts=self._scan_artifacts(workdir),
        )

    def _extract_metrics_from_output(self, output: str) -> Dict[str, float]:
        metrics: Dict[str, float] = {}

        common_patterns = [
            ("accuracy", r"[Aa]ccuracy[:\s]+([0-9.]+)"),
            ("f1", r"[Ff]1\D*?(\d+\.?\d*)"),
            ("precision", r"[Pp]recision[:\s]+([0-9.]+)"),
            ("recall", r"[Rr]ecall[:\s]+([0-9.]+)"),
            ("loss", r"[Ll]oss[:\s]+([0-9.]+)"),
            ("bleu", r"[Bb]leu[:\s]+([0-9.]+)"),
        ]

        import re
        for name, pattern in common_patterns:
            match = re.search(pattern, output)
            if match:
                try:
                    metrics[name] = float(match.group(1))
                except ValueError:
                    pass

        return metrics

    def _scan_artifacts(self, workdir: Path) -> Dict[str, str]:
        artifacts: Dict[str, str] = {}
        interesting = ["*.py", "*.json", "*.log", "*.csv", "*.txt", "*.pt", "*.pth", "*.bin"]
        for pattern in interesting:
            for f in workdir.glob(pattern):
                if f.name.startswith("_"):
                    continue
                artifacts[f.name] = str(f)
        return artifacts

    async def execute(self, spec: ExperimentSpec) -> ExperimentResult:
        workdir = self._prepare_workdir(spec)
        prompt = self._build_prompt(spec)
        timeout = spec.timeout_seconds or self.default_timeout

        last_result: Optional[ExperimentResult] = None
        retries = spec.max_retries if spec.max_retries > 0 else self.max_retries

        for attempt in range(retries):
            logger.info(
                "Experiment %s: attempt %d/%d in %s",
                spec.idea_id, attempt + 1, retries, workdir,
            )

            proc_result = await self._run_opencode(prompt, workdir, timeout)
            result = self._collect_results(workdir, proc_result)
            result.idea_id = spec.idea_id
            result.retry_count = attempt

            if result.status == ExecutionStatus.SUCCESS:
                logger.info("Experiment %s succeeded on attempt %d", spec.idea_id, attempt + 1)
                return result

            last_result = result

            if attempt < retries - 1:
                logger.warning(
                    "Experiment %s attempt %d failed: %s. Retrying...",
                    spec.idea_id, attempt + 1, result.error_message[:200],
                )
                error_ctx = f"""
## Previous Attempt Failed
Error: {result.error_message[:1000]}
Stdout tail: {result.stdout[-2000:] if result.stdout else "N/A"}
Stderr tail: {result.stderr[-2000:] if result.stderr else "N/A"}

Please fix the issues and try again. Make sure results.json is created.
"""
                prompt = prompt + "\n\n" + error_ctx
                await asyncio.sleep(5)

        logger.error("Experiment %s failed after %d retries", spec.idea_id, retries)
        if last_result:
            last_result.status = ExecutionStatus.FAILED
            return last_result

        return ExperimentResult(
            idea_id=spec.idea_id,
            status=ExecutionStatus.FAILED,
            error_message="All retry attempts exhausted",
            workdir=str(workdir),
        )


class SandboxExecutor(OpenCodeExecutor):
    """Execute experiments in an isolated environment (conda/venv)."""

    def __init__(self, env_manager_bin: str = "conda", **kwargs):
        super().__init__(**kwargs)
        self.env_manager_bin = env_manager_bin

    def _prepare_workdir(self, spec: ExperimentSpec) -> Path:
        workdir = super()._prepare_workdir(spec)

        env = spec.environment
        if env.env_type == EnvironmentType.CONDA and env.extra_packages:
            setup_script = workdir / "_setup_env.sh"
            pkgs = " ".join(env.extra_packages)
            setup_script.write_text(
                f"#!/bin/bash\n"
                f"set -e\n"
                f"eval \"$(conda shell.bash hook)\"\n"
                f"conda create -y -p ./env python={env.python_version} {pkgs}\n"
                f"conda activate ./env\n"
                f"pip install -r requirements.txt 2>/dev/null || true\n"
            )
            setup_script.chmod(0o755)

        return workdir

    async def _prepare_environment(self, workdir: Path, spec: ExperimentSpec) -> bool:
        env = spec.environment
        if not env.extra_packages:
            return True

        pip_cmd = ["pip", "install", "-q"] + env.extra_packages
        try:
            proc = await asyncio.create_subprocess_exec(
                *pip_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workdir),
            )
            await asyncio.wait_for(proc.communicate(), timeout=300)
            return proc.returncode == 0
        except Exception as e:
            logger.warning("Environment preparation failed: %s", e)
            return False

    async def execute(self, spec: ExperimentSpec) -> ExperimentResult:
        workdir = self._prepare_workdir(spec)

        env_ok = await self._prepare_environment(workdir, spec)
        if not env_ok:
            logger.warning("Environment setup had issues, proceeding anyway")

        return await super().execute(spec)


class ExperimentPipeline:
    """Orchestrate the full experiment lifecycle:
    opencode execution -> metric evaluation -> result aggregation.
    """

    def __init__(
        self,
        executor: OpenCodeExecutor,
        evaluator_config: Optional[Dict[str, Any]] = None,
    ):
        self.executor = executor
        self.evaluator_config = evaluator_config or {}

    async def run(self, spec: ExperimentSpec) -> ExperimentResult:
        start = time.monotonic()

        result = await self.executor.execute(spec)
        result.duration_seconds = time.monotonic() - start

        if result.status == ExecutionStatus.SUCCESS and result.predictions and result.labels:
            evaluated = await self._evaluate_result(result)
            result.metrics.update(evaluated.metrics)

        return result

    async def _evaluate_result(self, result: ExperimentResult) -> Any:
        from src.evaluator.evaluator import Evaluator, EvalConfig, TrainResult

        eval_config = EvalConfig(
            output_dir=str(Path(result.workdir) / "eval_output"),
            task_type=self.evaluator_config.get("task_type", "classification"),
            metrics=self.evaluator_config.get("metrics", []),
            generate_visualizations=self.evaluator_config.get("generate_visualizations", False),
            generate_report=self.evaluator_config.get("generate_report", False),
        )

        evaluator = Evaluator(eval_config)
        train_result = TrainResult(
            idea_id=result.idea_id,
            predictions=result.predictions,
            labels=result.labels,
        )

        return await evaluator.evaluate(train_result)

    async def run_batch(
        self,
        specs: List[ExperimentSpec],
        max_concurrent: int = 1,
    ) -> List[ExperimentResult]:
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _run_one(s: ExperimentSpec) -> ExperimentResult:
            async with semaphore:
                return await self.run(s)

        tasks = [_run_one(s) for s in specs]
        return await asyncio.gather(*tasks)
