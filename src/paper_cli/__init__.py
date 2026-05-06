"""paper_cli — opencode-driven paper writer.

The Python side does ONLY:
  1. Build an isolated workspace (skill files + arxiv template + user inputs).
  2. Invoke `opencode run` against the workspace.
  3. Verify the produced PDF.

All paper-writing logic (LaTeX drafting, citation, figures, compile-fix)
lives in the opencode session under workspace/skills/ and AGENTS.md.

Entry point: ``python -m paper_cli run --inputs <dir> --output <dir>``.
"""

__version__ = "0.1.0"
