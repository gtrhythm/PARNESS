"""Workspace bootstrap for an opencode paper-writing session.

Strong isolation: each run gets a fresh dir under ``output_root``. No symlinks
back to the main repo — only files explicitly copied in.

Layout produced::

  <workspace>/
    AGENTS.md                       # primary instruction doc
    .opencode/
      agent/paper-writer.md         # primary opencode agent definition
    skills/
      paper-writer.md
      latex-compile-fix.md
      tikz-figure.md
      s2-citation.md
      figure-image-generative.md
    inputs/                         # verbatim copy of user_inputs/
    paper/
      arxiv.sty                     # ready
      main.tex.skeleton             # opencode renames to main.tex and fills
      figs/                         # opencode writes figures here
    env.txt                         # readable summary of inherited env vars
"""

from __future__ import annotations

import shutil
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "templates"


def build(workspace: Path, user_inputs: Path, *, latex_service_url: str) -> None:
    """Materialize the workspace dir.

    Args:
        workspace: Target directory. Must not exist yet (fresh isolation).
        user_inputs: Directory containing user inputs (idea, results, metadata).
                     Copied verbatim into ``<workspace>/inputs/``.
        latex_service_url: URL of the LaTeX compiler service. Substituted into
                           AGENTS.md and exported via env.txt.
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
        TEMPLATES_DIR / ".opencode" / "agent" / "paper-writer.md",
        agent_dir / "paper-writer.md",
    )

    agents_md = (TEMPLATES_DIR / "AGENTS.md").read_text(encoding="utf-8")
    agents_md = agents_md.replace("{{LATEX_SERVICE_URL}}", latex_service_url)
    (workspace / "AGENTS.md").write_text(agents_md, encoding="utf-8")

    paper_dir = workspace / "paper"
    paper_dir.mkdir()
    (paper_dir / "figs").mkdir()
    shutil.copy2(TEMPLATES_DIR / "arxiv" / "arxiv.sty", paper_dir / "arxiv.sty")
    shutil.copy2(
        TEMPLATES_DIR / "arxiv" / "main.tex.skeleton",
        paper_dir / "main.tex.skeleton",
    )

    if not user_inputs.is_dir():
        raise FileNotFoundError(f"user inputs dir not found: {user_inputs}")
    shutil.copytree(user_inputs, workspace / "inputs")

    (workspace / "env.txt").write_text(
        "# Env vars the opencode session inherits from paper-cli (parent process):\n"
        f"LATEX_SERVICE_URL={latex_service_url}\n"
        "S2_API_KEY=<inherited if set; required for citation lookup>\n"
        "GRSAI_API_KEY=<inherited if set; optional, only needed for teaser images>\n",
        encoding="utf-8",
    )
