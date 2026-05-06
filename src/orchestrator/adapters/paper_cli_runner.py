"""paper_cli_runner — adapter that delegates Phase-4 paper writing to paper_cli.

Materializes a temporary ``inputs/`` directory from upstream pipeline state
(idea, experiment_report, experiment_results, paper_metadata), then invokes
``python -m src.paper_cli run`` as a subprocess. The opencode session inside
paper_cli does the actual LaTeX drafting, citation lookup, figure rendering,
and compile-fix loop.

Returns the path to the produced PDF and workspace.
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


def _dump_yaml(data: Any) -> str:
    """Minimal YAML dumper to avoid a hard pyyaml dep at import time.

    Falls back to pyyaml if available (and it always is in this repo, see
    pyproject.toml), but keeps the function callable when not.
    """
    try:
        import yaml
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    except ImportError:
        return json.dumps(data, ensure_ascii=False, indent=2)


def _idea_to_markdown(idea: Any) -> str:
    """Convert ``idea`` (dict or str) into the idea.md format paper_cli expects."""
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
        ("Motivation", "motivation"),
        ("Hypothesis", "hypothesis"),
        ("Method", "method"),
        ("Approach", "approach"),
        ("Contribution", "contribution"),
        ("Expected Outcome", "expected_outcome"),
    ]:
        val = idea.get(key)
        if val and isinstance(val, str):
            parts.append(f"## {label}\n\n{val}\n")

    if not parts:
        parts.append("# Idea\n")
        parts.append("```json\n" + json.dumps(idea, ensure_ascii=False, indent=2) + "\n```\n")

    return "\n".join(parts)


class PaperCliRunnerModule(BaseModule):
    """Run paper_cli (opencode-driven) to produce a compiled arxiv PDF.

    Inputs:
      - title              (str, required)        — paper title (best_selector.idea_title)
      - idea               (dict | str, required) — full idea object or description
      - experiment_report  (str, required)        — markdown report from experiment_report_generator
      - experiment_results (dict, optional)       — raw results dict
      - paper_metadata     (dict, optional)       — authors / affiliations / venue / keywords

    Params (from YAML node ``params``):
      - model              (str)  — opencode model id, default zai-coding-plan/glm-5.1
      - timeout_min        (int)  — paper_cli timeout, default 25
      - output_dir         (str)  — root for run workspaces, default output/auto_paper_e2e/papers
      - latex_service_url  (str)  — default http://localhost:9300

    Outputs:
      - pdf_path           (str)  — abs path to produced main.pdf, "" if missing
      - workspace          (str)  — abs path to run workspace
      - run_id             (str)  — subdir name (timestamp)
      - paper_cli_rc       (int)  — paper_cli subprocess return code
      - persistence_info   (dict)
    """

    module_name = "paper_cli_runner"

    INPUT_SPEC = {
        "title":              {"type": "str",  "required": True},
        "idea":               {"type": "any",  "required": True},
        "experiment_report":  {"type": "str",  "required": True},
        "experiment_results": {"type": "dict", "required": False, "default": {}},
        "paper_metadata":     {"type": "dict", "required": False, "default": {}},
    }
    OUTPUT_SPEC = {
        "pdf_path":         {"type": "str"},
        "workspace":        {"type": "str"},
        "run_id":           {"type": "str"},
        "paper_cli_rc":     {"type": "int"},
        "persistence_info": {"type": "dict"},
    }

    DEFAULTS = {
        "model": "zai-coding-plan/glm-5.1",
        "timeout_min": 25,
        "output_dir": "output/auto_paper_e2e/papers",
        "latex_service_url": "http://localhost:9300",
        # If True, paper_cli's stdout/stderr inherit the parent terminal
        # (good for interactive smoke runs). If False (default), they're
        # piped and saved to per-run log files (production / pipeline mode).
        "stream_output": False,
    }

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    def _resolve_param(self, key: str) -> Any:
        return self.config.get(key, self.DEFAULTS[key])

    def _materialize_inputs(
        self,
        *,
        title: str,
        idea: Any,
        experiment_report: str,
        experiment_results: Dict[str, Any],
        paper_metadata: Dict[str, Any],
    ) -> Path:
        """Build the ``inputs/`` directory paper_cli expects."""
        tmp = Path(tempfile.mkdtemp(prefix="paper_cli_runner_inputs_"))

        (tmp / "idea.md").write_text(_idea_to_markdown(idea), encoding="utf-8")

        (tmp / "results.json").write_text(
            json.dumps(experiment_results or {}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        (tmp / "results_report.md").write_text(experiment_report or "", encoding="utf-8")

        meta: Dict[str, Any] = dict(paper_metadata or {})
        meta.setdefault("title", title)
        meta.setdefault("authors", [{"name": "Auto Paper Machine", "corresponding": True}])
        meta.setdefault("target_venue", "arXiv preprint")
        (tmp / "metadata.yaml").write_text(_dump_yaml(meta), encoding="utf-8")

        return tmp

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.experiment_agents.persistence import PersistenceHelper

        title = inputs.get("title") or "Untitled Paper"
        idea = inputs.get("idea")
        experiment_report = inputs.get("experiment_report") or ""
        experiment_results = inputs.get("experiment_results") or {}
        paper_metadata = inputs.get("paper_metadata") or {}

        if not idea:
            raise ValueError("paper_cli_runner: 'idea' input is required")
        if not experiment_report:
            logger.warning("paper_cli_runner: empty experiment_report; paper will lack experiments section")

        model = self._resolve_param("model")
        timeout_min = int(self._resolve_param("timeout_min"))
        output_dir = self._resolve_param("output_dir")
        latex_service_url = self._resolve_param("latex_service_url")

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        run_id = time.strftime("%Y%m%d_%H%M%S")
        expected_workspace = Path(output_dir).resolve() / run_id

        inputs_dir = self._materialize_inputs(
            title=title,
            idea=idea,
            experiment_report=experiment_report,
            experiment_results=experiment_results,
            paper_metadata=paper_metadata,
        )

        cmd = [
            sys.executable, "-m", "src.paper_cli", "run",
            "--inputs", str(inputs_dir),
            "--output", str(output_dir),
            "--run-id", run_id,
            "--model", model,
            "--timeout-min", str(timeout_min),
            "--latex-service", latex_service_url,
        ]
        logger.info(
            "paper_cli_runner: invoking paper_cli (model=%s, timeout=%dmin, run_id=%s)",
            model, timeout_min, run_id,
        )

        stream_output = bool(self._resolve_param("stream_output"))
        pipe_kwargs: Dict[str, Any] = (
            {}
            if stream_output
            else {"stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.PIPE}
        )

        rc = -1
        stdout: bytes = b""
        stderr: bytes = b""
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
                logger.error("paper_cli_runner: hard timeout, killed paper_cli subprocess")
                rc = 124
                stdout, stderr = b"", b"timeout"
        finally:
            shutil.rmtree(inputs_dir, ignore_errors=True)

        pdf_path = expected_workspace / "paper" / "main.pdf"
        pdf_str = str(pdf_path) if pdf_path.is_file() else ""
        workspace_str = str(expected_workspace) if expected_workspace.is_dir() else ""

        log_dir = PersistenceHelper.make_output_dir("paper_cli_runner", run_id)
        PersistenceHelper.write_text(log_dir / "stdout.log", (stdout or b"").decode("utf-8", "replace"))
        PersistenceHelper.write_text(log_dir / "stderr.log", (stderr or b"").decode("utf-8", "replace"))

        persistence_info = PersistenceHelper.make_persistence_info(
            log_dir,
            {
                "pdf": pdf_str,
                "workspace": workspace_str,
                "stdout": str(log_dir / "stdout.log"),
                "stderr": str(log_dir / "stderr.log"),
            },
            session_id=run_id,
        )

        if not pdf_str:
            logger.warning(
                "paper_cli_runner: no PDF produced (rc=%s). workspace=%s",
                rc, workspace_str or "<missing>",
            )
        else:
            logger.info(
                "paper_cli_runner: PDF produced at %s (rc=%s, workspace=%s)",
                pdf_str, rc, workspace_str,
            )

        return {
            "pdf_path": pdf_str,
            "workspace": workspace_str,
            "run_id": run_id,
            "paper_cli_rc": rc,
            "persistence_info": persistence_info,
        }
