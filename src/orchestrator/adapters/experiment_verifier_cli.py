"""experiment_verifier_cli — adapter that judges runner output via opencode.

Reads the runner's workspace (results.json + execution.log + plan) and
emits a verdict (pass / retry / fail) with score + improvement
suggestions. Default model is ``zai-coding-plan/glm-5.1`` (200k context,
shares auth with the runner + paper writer — single source of failure).

Sits between ``experiment_runner_cli`` and ``experiment_success_gate``
in the YAML pipeline. Translates verifier verdict into the ``success``
boolean that ``experiment_success_gate`` already understands.
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


class ExperimentVerifierCliModule(BaseModule):
    """Verify a runner's experiment output via the experiment_verifier_cli.

    Inputs:
      - experiment_plan       (str, required)  — original plan markdown
      - runner_workspace      (str, required)  — abs path to runner's workspace
                                                  (containing work/results.json + work/execution.log)

    Params:
      - model                 (str)  — opencode model id (default zai-coding-plan/glm-5.1)
      - timeout_min           (int)  — verifier timeout (default 10)
      - output_dir            (str)  — default output/experiment_verifications
      - stream_output         (bool) — default False

    Outputs:
      - verdict               (str)            — "pass" / "retry" / "fail"
      - score                 (float)          — 0.0–1.0
      - reasoning             (str)            — verifier's analysis
      - evidence              (list[str])      — quoted log lines / facts
      - improvement_suggestions (list[str])    — for retry verdicts
      - success               (bool)           — verdict == "pass"
                                                  (consumed by experiment_success_gate)
      - workspace             (str)            — verifier's own workspace
      - run_id                (str)
      - persistence_info      (dict)
    """

    module_name = "experiment_verifier_cli"

    INPUT_SPEC = {
        "experiment_plan":  {"type": "str", "required": True},
        "runner_workspace": {"type": "str", "required": True},
    }
    OUTPUT_SPEC = {
        "verdict":                {"type": "str"},
        "score":                  {"type": "float"},
        "reasoning":              {"type": "str"},
        "evidence":               {"type": "list"},
        "improvement_suggestions": {"type": "list"},
        "success":                {"type": "bool"},
        "workspace":              {"type": "str"},
        "run_id":                 {"type": "str"},
        "persistence_info":       {"type": "dict"},
    }

    DEFAULTS = {
        # Use the same provider/model the rest of the pipeline is auth'd for.
        # opencode/minimax-m2.7 needed opencode.ai billing (we don't have);
        # zai-coding-plan/glm-5.1 has 200k context too, ample for log reading.
        "model": "zai-coding-plan/glm-5.1",
        "timeout_min": 10,
        "output_dir": "output/experiment_verifications",
        "stream_output": False,
    }

    FAIL_VERDICT_DEFAULTS = {
        "verdict": "fail",
        "score": 0.0,
        "reasoning": "verifier did not produce a verdict",
        "evidence": [],
        "improvement_suggestions": [],
    }

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    def _resolve(self, key: str) -> Any:
        return self.config.get(key, self.DEFAULTS[key])

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.experiment_agents.persistence import PersistenceHelper

        plan = inputs.get("experiment_plan") or ""
        runner_workspace_str = inputs.get("runner_workspace") or ""
        if not plan:
            raise ValueError("experiment_verifier_cli: 'experiment_plan' input is required")
        if not runner_workspace_str:
            # Runner produced nothing — short-circuit, don't even invoke opencode
            return self._short_circuit(
                "fail", 0.0,
                "runner_workspace is empty — runner produced no workspace at all",
                ["adapter received empty runner_workspace input"],
                ["fix experiment_runner_cli upstream — workspace not produced"],
            )
        runner_workspace = Path(runner_workspace_str)
        if not runner_workspace.is_dir():
            return self._short_circuit(
                "fail", 0.0,
                f"runner_workspace {runner_workspace_str} does not exist on disk",
                [f"path missing: {runner_workspace_str}"],
                ["ensure runner adapter wrote its workspace before verifier runs"],
            )

        model = self._resolve("model")
        timeout_min = int(self._resolve("timeout_min"))
        output_dir = self._resolve("output_dir")
        stream_output = bool(self._resolve("stream_output"))

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        run_id = time.strftime("%Y%m%d_%H%M%S")
        expected_workspace = Path(output_dir).resolve() / run_id

        plan_file = Path(tempfile.mkdtemp(prefix="experiment_verifier_plan_")) / "plan.md"
        plan_file.parent.mkdir(parents=True, exist_ok=True)
        plan_file.write_text(plan, encoding="utf-8")

        cmd = [
            sys.executable, "-m", "src.experiment_verifier_cli", "run",
            "--plan", str(plan_file),
            "--runner-workspace", str(runner_workspace.resolve()),
            "--output", str(output_dir),
            "--run-id", run_id,
            "--model", model,
            "--timeout-min", str(timeout_min),
        ]
        if stream_output:
            cmd.append("--stream-output")
        logger.info(
            "experiment_verifier_cli: invoking verifier CLI (model=%s, timeout=%dmin, run_id=%s)",
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
                logger.error("experiment_verifier_cli: hard timeout, killed subprocess")
                rc = 124
                stdout, stderr = b"", b"timeout"
        finally:
            shutil.rmtree(plan_file.parent, ignore_errors=True)

        verdict_path = expected_workspace / "verdict.json"
        verdict_data: Dict[str, Any] = dict(self.FAIL_VERDICT_DEFAULTS)
        if verdict_path.is_file():
            try:
                verdict_data.update(json.loads(verdict_path.read_text(encoding="utf-8")))
            except json.JSONDecodeError as e:
                logger.warning("experiment_verifier_cli: verdict.json malformed: %s", e)
                verdict_data["reasoning"] = f"verdict.json malformed: {e}"
        else:
            verdict_data["reasoning"] = (
                f"verifier did not produce verdict.json (subprocess rc={rc}); "
                "treating as fail"
            )

        verdict = verdict_data.get("verdict", "fail")
        try:
            score = float(verdict_data.get("score", 0.0) or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        reasoning = verdict_data.get("reasoning") or ""
        evidence = verdict_data.get("evidence") or []
        improvement_suggestions = verdict_data.get("improvement_suggestions") or []
        if not isinstance(evidence, list):
            evidence = [str(evidence)]
        if not isinstance(improvement_suggestions, list):
            improvement_suggestions = [str(improvement_suggestions)]

        log_dir = PersistenceHelper.make_output_dir("experiment_verifier_cli", run_id)
        PersistenceHelper.write_text(log_dir / "stdout.log", (stdout or b"").decode("utf-8", "replace"))
        PersistenceHelper.write_text(log_dir / "stderr.log", (stderr or b"").decode("utf-8", "replace"))
        if verdict_path.is_file():
            PersistenceHelper.write_text(log_dir / "verdict.json", verdict_path.read_text(encoding="utf-8"))

        persistence_info = PersistenceHelper.make_persistence_info(
            log_dir,
            {
                "workspace": str(expected_workspace) if expected_workspace.is_dir() else "",
                "verdict": str(verdict_path) if verdict_path.is_file() else "",
                "stdout": str(log_dir / "stdout.log"),
                "stderr": str(log_dir / "stderr.log"),
            },
            session_id=run_id,
        )

        success = (verdict == "pass")
        logger.info(
            "experiment_verifier_cli: verdict=%s score=%.2f success=%s rc=%s",
            verdict, score, success, rc,
        )

        return {
            "verdict": verdict,
            "score": score,
            "reasoning": reasoning,
            "evidence": evidence,
            "improvement_suggestions": improvement_suggestions,
            "success": success,
            "workspace": str(expected_workspace) if expected_workspace.is_dir() else "",
            "run_id": run_id,
            "persistence_info": persistence_info,
        }

    def _short_circuit(
        self,
        verdict: str,
        score: float,
        reasoning: str,
        evidence: list,
        suggestions: list,
    ) -> Dict[str, Any]:
        """Emit a verdict without invoking opencode (e.g. when runner produced nothing)."""
        return {
            "verdict": verdict,
            "score": score,
            "reasoning": reasoning,
            "evidence": evidence,
            "improvement_suggestions": suggestions,
            "success": verdict == "pass",
            "workspace": "",
            "run_id": time.strftime("%Y%m%d_%H%M%S"),
            "persistence_info": {"output_dir": "", "files": {}, "timestamp": "", "session_id": ""},
        }
