"""Workspace bootstrap for an opencode experiment-runner session.

Strong isolation: each run gets a fresh dir under ``output_root``. No
symlinks back to the main repo — only files explicitly copied in.

Layout produced::

  <workspace>/
    AGENTS.md                       # primary instruction doc
    .opencode/agent/runner.md       # opencode agent definition
    skills/
      experiment-runner.md          # orchestration playbook
      python-sandbox.md             # how to run code, capture output
      results-format.md             # results.json schema + invariants
    inputs/                         # verbatim copy of user_inputs/
      plan.md                       # the experiment plan
      idea.md (optional)
      resource_constraint.txt (optional)
    work/                           # opencode runs experiments here
      results.json                  # primary output (opencode writes)
      execution.log                 # primary output (opencode writes)
"""

from __future__ import annotations

import shutil
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "templates"


def build(workspace: Path, user_inputs: Path) -> None:
    """Materialize the workspace dir.

    Args:
        workspace: Target directory. Must not exist (fresh isolation).
        user_inputs: Directory with plan.md (required) + idea.md /
                     resource_constraint.txt (optional). Copied verbatim
                     into ``<workspace>/inputs/``.
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
        TEMPLATES_DIR / ".opencode" / "agent" / "runner.md",
        agent_dir / "runner.md",
    )

    shutil.copy2(TEMPLATES_DIR / "AGENTS.md", workspace / "AGENTS.md")

    if not user_inputs.is_dir():
        raise FileNotFoundError(f"user inputs dir not found: {user_inputs}")
    shutil.copytree(user_inputs, workspace / "inputs")

    (workspace / "work").mkdir()
