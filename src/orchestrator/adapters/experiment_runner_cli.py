"""experiment_runner_cli — adapter that delegates Phase-3 experiment execution
to ``src.experiment_runner_cli`` (an opencode session inside an isolated
workspace).

Replaces ``experiment_executor_opencode`` (which uses the broken
OpenCodeClient ``--attach`` protocol → "Session not found" failures).
This adapter follows the proven paper_cli_runner.py pattern: materialize
inputs as files, invoke the CLI as a subprocess.

Returns the runner's workspace path + parsed results so a downstream
verifier can read both.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseModule

logger = logging.getLogger(__name__)


def _idea_to_markdown(idea: Any) -> str:
    """Convert ``idea`` (dict or str) into idea.md content."""
    if isinstance(idea, str):
        return idea
    if not isinstance(idea, dict):
        return str(idea)
    parts: list[str] = []
    title = idea.get("title") or idea.get("idea_title") or idea.get("name")
    if title:
        parts.append(f"# {title}\n")
    for label, key in [
        ("Description", "description"),
        ("Description", "idea_description"),
        ("Method", "method"),
        ("Hypothesis", "hypothesis"),
    ]:
        v = idea.get(key)
        if isinstance(v, str) and v:
            parts.append(f"## {label}\n\n{v}\n")
    if not parts:
        parts.append("# Idea\n\n```json\n" + json.dumps(idea, ensure_ascii=False, indent=2) + "\n```\n")
    return "\n".join(parts)


class ExperimentRunnerCliModule(BaseModule):
    """Run an experiment via the experiment_runner_cli (opencode subprocess).

    Inputs:
      - experiment_plan    (str, required)        — markdown plan
      - idea               (any, optional)        — best_idea object/string for context
      - resource_constraint (str, optional)       — e.g. "single V100 32GB"

    Params:
      - model              (str)  — opencode model id, default zai-coding-plan/glm-5.1
      - timeout_min        (int)  — runner timeout, default 60
      - output_dir         (str)  — root for run workspaces, default output/experiments
      - stream_output      (bool) — inherit stdout/stderr (default False)

    Outputs:
      - success            (bool)         — true iff results.json + execution.log present
      - experiment_results (dict)         — parsed work/results.json (or {})
      - execution_log      (str)          — work/execution.log contents
      - workspace          (str)          — abs path to runner's workspace
      - run_id             (str)
      - runner_cli_rc      (int)
      - persistence_info   (dict)
    """

    module_name = "experiment_runner_cli"

    INPUT_SPEC = {
        "experiment_plan":     {"type": "str",  "required": True},
        "idea":                {"type": "any",  "required": False, "default": ""},
        "resource_constraint": {"type": "str",  "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "success":            {"type": "bool"},
        "experiment_results": {"type": "dict"},
        "execution_log":      {"type": "str"},
        "workspace":          {"type": "str"},
        "run_id":             {"type": "str"},
        "runner_cli_rc":      {"type": "int"},
        "persistence_info":   {"type": "dict"},
    }

    DEFAULTS = {
        "model": "zai-coding-plan/glm-5.1",
        "timeout_min": 60,
        "output_dir": "output/experiments",
        "stream_output": False,
    }

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    def _resolve(self, key: str) -> Any:
        return self.config.get(key, self.DEFAULTS[key])

    def _materialize_inputs(
        self,
        *,
        plan: str,
        idea: Any,
        resource_constraint: str,
    ) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="experiment_runner_inputs_"))
        (tmp / "plan.md").write_text(plan or "", encoding="utf-8")
        if idea:
            (tmp / "idea.md").write_text(_idea_to_markdown(idea), encoding="utf-8")
        if resource_constraint:
            (tmp / "resource_constraint.txt").write_text(resource_constraint, encoding="utf-8")
        return tmp

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.experiment_agents.persistence import PersistenceHelper

        plan = inputs.get("experiment_plan") or ""
        if not plan:
            raise ValueError("experiment_runner_cli: 'experiment_plan' input is required")
        idea = inputs.get("idea") or ""
        resource_constraint = inputs.get("resource_constraint") or ""

        model = self._resolve("model")
        timeout_min = int(self._resolve("timeout_min"))
        output_dir = self._resolve("output_dir")
        stream_output = bool(self._resolve("stream_output"))

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        run_id = time.strftime("%Y%m%d_%H%M%S")
        expected_workspace = Path(output_dir).resolve() / run_id

        inputs_dir = self._materialize_inputs(
            plan=plan, idea=idea, resource_constraint=resource_constraint,
        )

        cmd = [
            sys.executable, "-m", "src.experiment_runner_cli", "run",
            "--inputs", str(inputs_dir),
            "--output", str(output_dir),
            "--run-id", run_id,
            "--model", model,
            "--timeout-min", str(timeout_min),
        ]
        if stream_output:
            cmd.append("--stream-output")
        logger.info(
            "experiment_runner_cli: invoking runner CLI (model=%s, timeout=%dmin, run_id=%s)",
            model, timeout_min, run_id,
        )

        rc = -1
        stdout = stderr = b""
        pipe_kwargs: Dict[str, Any] = (
            {} if stream_output
            else {"stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.PIPE}
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(Path(__file__).resolve().parents[3]),
                env=os.environ.copy(),
                **pipe_kwargs,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=(timeout_min + 2) * 60,
                )
                rc = proc.returncode if proc.returncode is not None else -1
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                logger.error("experiment_runner_cli: hard timeout, killed subprocess")
                rc = 124
                stdout, stderr = b"", b"timeout"
        finally:
            shutil.rmtree(inputs_dir, ignore_errors=True)

        results_path = expected_workspace / "work" / "results.json"
        log_path = expected_workspace / "work" / "execution.log"

        experiment_results: Dict[str, Any] = {}
        if results_path.is_file():
            try:
                experiment_results = json.loads(results_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                logger.warning("experiment_runner_cli: results.json malformed: %s", e)
                experiment_results = {"_status": "malformed", "error": str(e)}
        execution_log = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""

        success = bool(results_path.is_file() and log_path.is_file()
                       and experiment_results.get("_status") in ("pass", "partial"))

        log_dir = PersistenceHelper.make_output_dir("experiment_runner_cli", run_id)
        PersistenceHelper.write_text(log_dir / "stdout.log", (stdout or b"").decode("utf-8", "replace"))
        PersistenceHelper.write_text(log_dir / "stderr.log", (stderr or b"").decode("utf-8", "replace"))

        persistence_info = PersistenceHelper.make_persistence_info(
            log_dir,
            {
                "workspace": str(expected_workspace) if expected_workspace.is_dir() else "",
                "results_json": str(results_path) if results_path.is_file() else "",
                "execution_log": str(log_path) if log_path.is_file() else "",
                "stdout": str(log_dir / "stdout.log"),
                "stderr": str(log_dir / "stderr.log"),
            },
            session_id=run_id,
        )

        logger.info(
            "experiment_runner_cli: success=%s, rc=%s, status=%s, workspace=%s",
            success, rc, experiment_results.get("_status", "?"),
            str(expected_workspace) if expected_workspace.is_dir() else "<missing>",
        )

        return {
            "success": success,
            "experiment_results": experiment_results,
            "execution_log": execution_log,
            "workspace": str(expected_workspace) if expected_workspace.is_dir() else "",
            "run_id": run_id,
            "runner_cli_rc": rc,
            "persistence_info": persistence_info,
        }
