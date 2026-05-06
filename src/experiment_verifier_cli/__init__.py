"""experiment_verifier_cli — opencode-driven experiment result verifier.

Reads the runner's workspace (results.json + execution.log) and emits a
verdict (pass / retry / fail) with score + improvement suggestions. Also
mirrors the paper_cli pattern.

Default model is ``zai-coding-plan/glm-5.1`` (200k context, single-provider
auth shared with the runner / paper writer). Originally we had picked a
minimax variant for reasoning strength, but it required separate billing
that we don't have, causing 100% silent failure — see git history.

Entry point: ``python -m src.experiment_verifier_cli run --runner-workspace <dir> --output <dir>``.
"""

__version__ = "0.1.0"
