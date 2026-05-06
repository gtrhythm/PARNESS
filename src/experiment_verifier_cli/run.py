"""CLI entry point: ``python -m src.experiment_verifier_cli run --plan <file> --runner-workspace <dir> --output <dir>``.

Bootstraps a verifier workspace (which includes a copy of the runner's
workspace under inputs/) and runs an opencode session that emits a
verdict.json.
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

# NOTE: opencode/minimax-m2.7 requires opencode.ai billing which we don't have;
# zai-coding-plan/glm-5.1 has the same 200k context window and is auth'd for
# the rest of the pipeline.
DEFAULT_MODEL = "zai-coding-plan/glm-5.1"
DEFAULT_TIMEOUT_MIN = 10

REPO_ROOT = Path(__file__).resolve().parents[2]

INITIAL_PROMPT = (
    "Read AGENTS.md, the plan in inputs/plan.md, and the runner's outputs in "
    "inputs/runner_workspace/work/. Decide whether the experiment passed, "
    "needs retry, or should be given up on. Write your decision to verdict.json "
    "following the schema in skills/verdict-emitter.md. End the session when "
    "verdict.json is written."
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
    plan: Path,
    runner_workspace: Path,
    output_root: Path,
    *,
    run_id: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    timeout_min: int = DEFAULT_TIMEOUT_MIN,
    skip_opencode: bool = False,
    stream_output: bool = False,
) -> Path:
    if not plan.is_file():
        raise SystemExit(f"plan file not found: {plan}")
    if not runner_workspace.is_dir():
        raise SystemExit(f"runner workspace not a directory: {runner_workspace}")

    run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
    workspace_dir = (output_root / run_id).resolve()
    if workspace_dir.exists():
        raise SystemExit(f"workspace already exists: {workspace_dir}")

    print(f"[exp-verifier-cli] bootstrapping workspace: {workspace_dir}", file=sys.stderr)
    ws.build(workspace_dir, plan, runner_workspace)
    print("[exp-verifier-cli] workspace ready", file=sys.stderr)

    if skip_opencode:
        print(
            f"[exp-verifier-cli] --skip-opencode set; not invoking opencode. "
            f"Workspace at {workspace_dir}",
            file=sys.stderr,
        )
        return workspace_dir

    env = os.environ.copy()
    loaded = _load_dotenv(REPO_ROOT / ".env", env)
    if loaded:
        print(f"[exp-verifier-cli] loaded {loaded} key(s) from .env", file=sys.stderr)

    cmd = [
        "opencode", "run",
        "--dir", str(workspace_dir),
        "--agent", "verifier",
        "--model", model,
        "--dangerously-skip-permissions",
        INITIAL_PROMPT,
    ]
    print(
        f"[exp-verifier-cli] launching opencode (model={model}, timeout={timeout_min}min)",
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
            f"[exp-verifier-cli] TIMEOUT after {timeout_min}min; workspace preserved at {workspace_dir}",
            file=sys.stderr,
        )
        rc = 124

    verdict = workspace_dir / "verdict.json"
    if verdict.exists():
        print(
            f"[exp-verifier-cli] OK verdict.json produced ({verdict.stat().st_size}B)",
            file=sys.stderr,
        )
    else:
        print(
            f"[exp-verifier-cli] WARNING: no verdict.json (rc={rc})",
            file=sys.stderr,
        )

    return workspace_dir


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="exp-verifier-cli", description="opencode-driven experiment verifier",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="verify an experiment")
    p_run.add_argument("--plan", type=Path, required=True, help="original plan markdown")
    p_run.add_argument(
        "--runner-workspace", type=Path, required=True,
        help="runner's workspace dir (containing work/results.json + work/execution.log)",
    )
    p_run.add_argument(
        "--output", type=Path, default=Path("output/experiment_verifications"),
    )
    p_run.add_argument("--run-id", default=None)
    p_run.add_argument("--model", default=DEFAULT_MODEL)
    p_run.add_argument("--timeout-min", type=int, default=DEFAULT_TIMEOUT_MIN)
    p_run.add_argument("--skip-opencode", action="store_true")
    p_run.add_argument("--stream-output", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "run":
        run(
            plan=args.plan, runner_workspace=args.runner_workspace,
            output_root=args.output, run_id=args.run_id,
            model=args.model, timeout_min=args.timeout_min,
            skip_opencode=args.skip_opencode, stream_output=args.stream_output,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
