r"""DEPRECATED — opencode HTTP-attach client with broken session protocol.

This client invokes ``opencode run --attach <server_url>`` against a
locally-spawned opencode server. The protocol is broken in opencode
1.14.x: the client issues a ``run`` request without first creating a
session, so the server returns 404 ``Session not found`` and every
invocation fails in ~1.5s with zero LLM activity.

Confirmed reproductions: 12 consecutive failures across multiple days
(May 3 → May 5, 2026), all ``session_id=''``, ``total_tokens=0``,
``error="Session not found"``.

**Use one of these instead:**

- ``src.experiment_runner_cli`` (CLI) +
  ``src.orchestrator.adapters.experiment_runner_cli`` (adapter) — proven
  pattern: each invocation is a fresh ``opencode run`` subprocess, no
  HTTP-attach. See ``config/pipelines/auto_paper_e2e_opencode.yaml``.
- ``src.experiment_verifier_cli`` for the verification half.
- ``src.paper_cli`` + ``src.orchestrator.adapters.paper_cli_runner``
  for the parallel paper-writing case.

This module is kept for now to avoid breaking import paths; do **not**
add new callers. To safely retire, audit:

    grep -rn "OpenCodeClient\|experiment_executor_opencode" src/ config/

and migrate each remaining caller to a CLI-based adapter.
"""

import asyncio
import json
import logging
import uuid
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

warnings.warn(
    "src.experiment_agents.opencode_client.OpenCodeClient uses a broken "
    "--attach session protocol that fails with 'Session not found'. "
    "Use src.experiment_runner_cli + src.experiment_verifier_cli (CLI-based) instead.",
    DeprecationWarning,
    stacklevel=2,
)


@dataclass
class OpenCodeResult:
    session_id: str = ""
    text: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    success: bool = False
    error: str = ""


class OpenCodeOutputParser:
    def parse(self, ndjson_lines: List[str]) -> OpenCodeResult:
        texts = []
        tool_calls = []
        session_id = ""
        total_tokens = 0

        for line in ndjson_lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")

            if event_type == "step_start":
                session_id = event.get("sessionID", "")
            elif event_type == "text":
                texts.append(event.get("part", {}).get("text", ""))
            elif event_type == "tool_use":
                state = event.get("part", {}).get("state", {})
                tool_calls.append({
                    "tool": event.get("part", {}).get("tool", ""),
                    "status": state.get("status"),
                    "input": state.get("input", {}),
                    "output": state.get("output", ""),
                })
            elif event_type == "step_finish":
                tokens = event.get("part", {}).get("tokens", {})
                total_tokens += tokens.get("total", 0)

        return OpenCodeResult(
            session_id=session_id,
            text="\n".join(texts),
            tool_calls=tool_calls,
            total_tokens=total_tokens,
        )


class OpenCodeClient:
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.server_url = ""
        self._server_proc = None

    async def ensure_server(self) -> str:
        server_url = self.config.get("server", {}).get("url", "http://127.0.0.1:4096")
        host = self.config.get("server", {}).get("host", "127.0.0.1")
        port = self.config.get("server", {}).get("port", 4096)
        auto_start = self.config.get("server", {}).get("auto_start", False)

        if auto_start:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "opencode", "serve", "--port", str(port),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.sleep(2)
                self._server_proc = proc
                server_url = f"http://{host}:{port}"
            except FileNotFoundError:
                logger.warning("opencode binary not found, server auto-start skipped")

        self.server_url = server_url
        return server_url

    async def run(
        self,
        prompt: str,
        workdir: str,
        model: str = "",
        agent: str = "build",
        timeout: int = 3600,
        session_id: str = "",
    ) -> OpenCodeResult:
        parser = OpenCodeOutputParser()

        cmd = ["opencode", "run", "--format", "json"]
        if self.server_url:
            cmd.extend(["--attach", self.server_url])
        cmd.extend(["--dir", workdir])
        if model:
            cmd.extend(["--model", model])
        if session_id:
            cmd.extend(["--session", session_id])
        cmd.append(prompt)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                return OpenCodeResult(
                    success=False,
                    error=f"opencode run timed out after {timeout}s",
                )

            if not stdout:
                return OpenCodeResult(
                    success=False,
                    error=stderr.decode("utf-8", errors="replace") if stderr else "no output",
                )

            lines = stdout.decode("utf-8", errors="replace").splitlines()
            result = parser.parse(lines)
            result.success = proc.returncode == 0
            if not result.success and not result.error:
                result.error = stderr.decode("utf-8", errors="replace") if stderr else f"exit code {proc.returncode}"
            return result

        except FileNotFoundError:
            return OpenCodeResult(success=False, error="opencode binary not found")
        except Exception as e:
            return OpenCodeResult(success=False, error=str(e))

    async def create_workspace(self, prefix: str = "exp") -> str:
        base_dir = self.config.get("workspace", {}).get(
            "base_dir", "output/opencode_workspaces"
        )
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:8]
        ws_dir = Path(base_dir) / f"{prefix}_{ts}_{uid}"
        ws_dir.mkdir(parents=True, exist_ok=True)
        return str(ws_dir)

    async def cleanup_workspace(self, workdir: str) -> None:
        import shutil
        p = Path(workdir).resolve()
        # 安全检查：只允许清理 output/ 下的实验工作目录
        allowed_root = Path("output").resolve()
        if not str(p).startswith(str(allowed_root)):
            raise RuntimeError(
                f"cleanup_workspace 拒绝删除 output/ 以外的目录: {p}"
            )
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)

    async def shutdown_server(self) -> None:
        if self._server_proc and self._server_proc.returncode is None:
            self._server_proc.terminate()
            try:
                await asyncio.wait_for(self._server_proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._server_proc.kill()
            self._server_proc = None
