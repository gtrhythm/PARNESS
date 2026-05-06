"""Workspace bootstrap for an opencode experiment-verifier session.

Layout produced::

  <workspace>/
    AGENTS.md                         # primary instruction doc
    .opencode/agent/verifier.md       # opencode agent definition
    skills/
      result-validator.md             # check schema / sanity / NaN
      log-analyzer.md                 # parse execution.log for failures
      verdict-emitter.md              # final output format
    inputs/
      plan.md                         # original experiment plan
      runner_workspace/               # runner's full workspace, copied READ-ONLY
        work/
          results.json
          execution.log
        ...
    verdict.json                      # opencode writes here (final output)
"""

from __future__ import annotations

import shutil
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "templates"


def build(workspace: Path, plan_path: Path, runner_workspace: Path) -> None:
    """Materialize the workspace dir.

    Args:
        workspace: Target directory. Must not exist (fresh isolation).
        plan_path: Path to the original experiment plan markdown.
        runner_workspace: Path to the runner's workspace dir to be inspected.
    """
    workspace.mkdir(parents=True, exist_ok=False)

    skills_dir = workspace / "skills"
    skills_dir.mkdir()
    for skill_file in (TEMPLATES_DIR / "skills").iterdir():
        if skill_file.is_file():
            shutil.copy2(skill_file, skills_dir / skill_file.name)

    agent_dir = workspace / ".opencode" / "agent"
    agent_dir.mkdir(parents=True)
    shutil.copy2(
        TEMPLATES_DIR / ".opencode" / "agent" / "verifier.md",
        agent_dir / "verifier.md",
    )

    shutil.copy2(TEMPLATES_DIR / "AGENTS.md", workspace / "AGENTS.md")

    inputs_dir = workspace / "inputs"
    inputs_dir.mkdir()

    if not plan_path.is_file():
        raise FileNotFoundError(f"plan file not found: {plan_path}")
    shutil.copy2(plan_path, inputs_dir / "plan.md")

    if not runner_workspace.is_dir():
        raise FileNotFoundError(f"runner_workspace not a directory: {runner_workspace}")
    shutil.copytree(runner_workspace, inputs_dir / "runner_workspace")
