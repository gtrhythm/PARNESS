"""experiment_runner_cli — opencode-driven experiment executor.

Mirrors the paper_cli pattern: bootstraps an isolated workspace, drops in
skill files + an opencode agent definition, then invokes ``opencode run``
as a subprocess. The opencode session inside writes/runs experiment code
and dumps results.json + execution.log.

Bypasses src/experiment_agents/opencode_client.py (whose --attach session
protocol is broken — see deprecation notice on OpenCodeClient).

Entry point: ``python -m src.experiment_runner_cli run --plan <file> --output <dir>``.
"""

__version__ = "0.1.0"
