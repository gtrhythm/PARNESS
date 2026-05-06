"""CLI entry point: ``python -m paper_cli run --inputs <dir> --output <dir>``.

Bootstraps an isolated workspace and delegates the actual paper writing to an
opencode session running inside that workspace.
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
DEFAULT_TIMEOUT_MIN = 20
DEFAULT_LATEX_URL = "http://localhost:9300"

# Repo root = three levels up from this file (src/paper_cli/run.py → repo).
REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path, env: dict) -> int:
    """Load KEY=VALUE pairs from ``path`` into ``env`` if not already set.

    Returns the count of newly-set keys. Existing env vars are NOT overwritten,
    so an explicit ``export`` in the user's shell wins over the .env file.
    Lines starting with ``#`` and blank lines are ignored.
    """
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

INITIAL_PROMPT = (
    "Read AGENTS.md and the files under inputs/. "
    "Write the arxiv-style paper end-to-end into paper/. "
    "Compile via the LaTeX service (URL in $LATEX_SERVICE_URL) until returncode=0. "
    "Final artifact: paper/main.pdf. End the session when done."
)


def run(
    inputs: Path,
    output_root: Path,
    *,
    run_id: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    timeout_min: int = DEFAULT_TIMEOUT_MIN,
    skip_opencode: bool = False,
    latex_service_url: str = DEFAULT_LATEX_URL,
) -> Path:
    """Bootstrap a workspace and invoke opencode. Returns workspace path."""
    if not inputs.is_dir():
        raise SystemExit(f"inputs dir not found: {inputs}")

    run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
    # Resolve to absolute up-front so opencode's --dir works regardless of the
    # subprocess's cwd. Path.resolve(strict=False) tolerates non-existent paths.
    workspace_dir = (output_root / run_id).resolve()
    if workspace_dir.exists():
        raise SystemExit(f"workspace already exists: {workspace_dir}")

    print(f"[paper-cli] bootstrapping workspace: {workspace_dir}", file=sys.stderr)
    ws.build(workspace_dir, inputs, latex_service_url=latex_service_url)
    print(f"[paper-cli] workspace ready", file=sys.stderr)

    if skip_opencode:
        print(
            f"[paper-cli] --skip-opencode set; not invoking opencode. "
            f"Workspace at {workspace_dir}",
            file=sys.stderr,
        )
        return workspace_dir

    env = os.environ.copy()
    env["LATEX_SERVICE_URL"] = latex_service_url
    dotenv_path = REPO_ROOT / ".env"
    loaded = _load_dotenv(dotenv_path, env)
    if loaded:
        print(f"[paper-cli] loaded {loaded} key(s) from {dotenv_path}", file=sys.stderr)
    if "S2_API_KEY" not in env or not env.get("S2_API_KEY"):
        print(
            "[paper-cli] WARNING: S2_API_KEY not in env or .env; citation lookup will fail. "
            "Export it before running, or accept that the paper will lack references.",
            file=sys.stderr,
        )

    cmd = [
        "opencode", "run",
        "--dir", str(workspace_dir),
        "--agent", "paper-writer",
        "--model", model,
        "--dangerously-skip-permissions",
        INITIAL_PROMPT,
    ]
    print(
        f"[paper-cli] launching opencode (model={model}, timeout={timeout_min}min)",
        file=sys.stderr,
    )

    rc = -1
    try:
        result = subprocess.run(
            cmd, env=env, timeout=timeout_min * 60, cwd=str(workspace_dir),
        )
        rc = result.returncode
    except subprocess.TimeoutExpired:
        print(
            f"[paper-cli] TIMEOUT after {timeout_min}min; workspace preserved at {workspace_dir}",
            file=sys.stderr,
        )
        rc = 124

    pdf = workspace_dir / "paper" / "main.pdf"
    if pdf.exists():
        size = pdf.stat().st_size
        print(
            f"[paper-cli] OK main.pdf produced ({size} bytes) at {pdf}",
            file=sys.stderr,
        )
    else:
        print(
            f"[paper-cli] WARNING: no main.pdf at {pdf} (opencode rc={rc}). "
            f"Inspect the workspace for partial state.",
            file=sys.stderr,
        )

    return workspace_dir


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="paper-cli", description="opencode-driven arxiv-style paper writer",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="run a paper-writing session")
    p_run.add_argument(
        "--inputs", type=Path, required=True,
        help="dir containing idea / results / metadata (see src/paper_cli/example_inputs/)",
    )
    p_run.add_argument(
        "--output", type=Path, default=Path("output/papers"),
        help="root dir for run workspaces (default: output/papers)",
    )
    p_run.add_argument(
        "--run-id", default=None, help="override timestamp run id",
    )
    p_run.add_argument("--model", default=DEFAULT_MODEL)
    p_run.add_argument("--timeout-min", type=int, default=DEFAULT_TIMEOUT_MIN)
    p_run.add_argument(
        "--skip-opencode", action="store_true",
        help="bootstrap the workspace only; don't invoke opencode (useful for tests)",
    )
    p_run.add_argument("--latex-service", default=DEFAULT_LATEX_URL)

    args = parser.parse_args(argv)
    if args.cmd == "run":
        run(
            inputs=args.inputs,
            output_root=args.output,
            run_id=args.run_id,
            model=args.model,
            timeout_min=args.timeout_min,
            skip_opencode=args.skip_opencode,
            latex_service_url=args.latex_service,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
