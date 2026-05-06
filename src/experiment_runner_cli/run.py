"""CLI entry point: ``python -m src.experiment_runner_cli run --inputs <dir> --output <dir>``.

Bootstraps an isolated workspace and delegates experiment execution to
an opencode session (model defaults to a code-strong one).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from . import workspace as ws

DEFAULT_MODEL = "zai-coding-plan/glm-5.1"
DEFAULT_TIMEOUT_MIN = 60

REPO_ROOT = Path(__file__).resolve().parents[2]

INITIAL_PROMPT = (
    "Read AGENTS.md and the files under inputs/. "
    "Implement and run the experiment in work/, following the plan in inputs/plan.md. "
    "Save the structured results to work/results.json and the full log to "
    "work/execution.log. End the session when both files exist and "
    "results.json passes the schema in skills/results-format.md."
)


def _load_dotenv(path: Path, env: dict) -> int:
    if not path.is_file():
        return 0
    added = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip().strip('"').strip("'")
        if key not in env or not env[key]:
            env[key] = value
            added += 1
    return added


def run(
    inputs: Path,
    output_root: Path,
    *,
    run_id: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    timeout_min: int = DEFAULT_TIMEOUT_MIN,
    skip_opencode: bool = False,
    stream_output: bool = False,
) -> Path:
    """Bootstrap a workspace and invoke opencode. Returns workspace path."""
    if not inputs.is_dir():
        raise SystemExit(f"inputs dir not found: {inputs}")

    run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
    workspace_dir = (output_root / run_id).resolve()
    if workspace_dir.exists():
        raise SystemExit(f"workspace already exists: {workspace_dir}")

    print(f"[exp-runner-cli] bootstrapping workspace: {workspace_dir}", file=sys.stderr)
    ws.build(workspace_dir, inputs)
    print("[exp-runner-cli] workspace ready", file=sys.stderr)

    if skip_opencode:
        print(
            f"[exp-runner-cli] --skip-opencode set; not invoking opencode. "
            f"Workspace at {workspace_dir}",
            file=sys.stderr,
        )
        return workspace_dir

    env = os.environ.copy()
    loaded = _load_dotenv(REPO_ROOT / ".env", env)
    if loaded:
        print(f"[exp-runner-cli] loaded {loaded} key(s) from .env", file=sys.stderr)

    cmd = [
        "opencode", "run",
        "--dir", str(workspace_dir),
        "--agent", "runner",
        "--model", model,
        "--dangerously-skip-permissions",
        INITIAL_PROMPT,
    ]
    print(
        f"[exp-runner-cli] launching opencode (model={model}, timeout={timeout_min}min)",
        file=sys.stderr,
    )

    rc = -1
    pipe_kwargs = (
        {} if stream_output
        else {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    )
    try:
        result = subprocess.run(
            cmd, env=env, timeout=timeout_min * 60, cwd=str(workspace_dir),
            **pipe_kwargs,
        )
        rc = result.returncode
    except subprocess.TimeoutExpired:
        print(
            f"[exp-runner-cli] TIMEOUT after {timeout_min}min; workspace preserved at {workspace_dir}",
            file=sys.stderr,
        )
        rc = 124

    results = workspace_dir / "work" / "results.json"
    log = workspace_dir / "work" / "execution.log"
    if results.exists() and log.exists():
        print(
            f"[exp-runner-cli] OK results.json + execution.log produced ({results.stat().st_size}B + {log.stat().st_size}B)",
            file=sys.stderr,
        )
    else:
        print(
            f"[exp-runner-cli] WARNING: missing artifacts (results={results.exists()}, log={log.exists()}, rc={rc})",
            file=sys.stderr,
        )

    return workspace_dir


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="exp-runner-cli", description="opencode-driven experiment runner",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="run an experiment")
    p_run.add_argument(
        "--inputs", type=Path, required=True,
        help="dir containing plan.md (required) + optional idea.md / resource_constraint.txt",
    )
    p_run.add_argument(
        "--output", type=Path, default=Path("output/experiments"),
        help="root dir for run workspaces",
    )
    p_run.add_argument("--run-id", default=None)
    p_run.add_argument("--model", default=DEFAULT_MODEL)
    p_run.add_argument("--timeout-min", type=int, default=DEFAULT_TIMEOUT_MIN)
    p_run.add_argument(
        "--skip-opencode", action="store_true",
        help="bootstrap workspace only; useful for tests",
    )
    p_run.add_argument(
        "--stream-output", action="store_true",
        help="inherit opencode stdout/stderr (interactive smoke runs)",
    )

    args = parser.parse_args(argv)
    if args.cmd == "run":
        run(
            inputs=args.inputs, output_root=args.output, run_id=args.run_id,
            model=args.model, timeout_min=args.timeout_min,
            skip_opencode=args.skip_opencode, stream_output=args.stream_output,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
