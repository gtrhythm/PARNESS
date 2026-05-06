"""Stop a running PEK daemon and clear its state file.

Tries graceful RPC shutdown first; falls back to SIGTERM, then SIGKILL.
Always removes ``state.json`` at the end so subsequent ``pek_start``
calls boot a fresh daemon cleanly.

Idempotent: if no daemon is recorded or the recorded PID is already
dead, the module reports ``already_stopped`` instead of failing.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from typing import Any, Dict, Optional

from .base import BaseModule
from ..monitoring.reporter import AgentOutput

from src.pdf_parser.daemon.client import DaemonError, PEKClient
from src.pdf_parser.daemon.state import (
    clear_state,
    is_pid_alive,
    read_state,
)

logger = logging.getLogger(__name__)


DEFAULT_STATE_DIR = "output/pek_daemon"
DEFAULT_GRACE_SECONDS = 30.0
DEFAULT_KILL_GRACE_SECONDS = 5.0


class PEKStopModule(BaseModule):
    module_name = "pek_stop"

    INPUT_SPEC = {
        "state_dir": {"type": "str", "required": False, "default": ""},
        "grace_seconds": {"type": "float", "required": False, "default": 0.0},
    }
    OUTPUT_SPEC = {
        "stopped": {"type": "bool"},
        "method": {"type": "str"},     # rpc | sigterm | sigkill | already_stopped
        "pid": {"type": "int"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        state_dir = (
            inputs.get("state_dir")
            or self.config.get("state_dir")
            or DEFAULT_STATE_DIR
        )
        grace = float(
            inputs.get("grace_seconds")
            or self.config.get("grace_seconds")
            or DEFAULT_GRACE_SECONDS
        )

        state = read_state(state_dir)
        if state is None:
            logger.info("PEK daemon: no state file at %s — nothing to stop", state_dir)
            return {"stopped": True, "method": "already_stopped", "pid": -1}

        if not is_pid_alive(state.pid):
            logger.info(
                "PEK daemon pid=%d already gone — clearing stale state",
                state.pid,
            )
            clear_state(state_dir)
            return {"stopped": True, "method": "already_stopped", "pid": state.pid}

        # 1. Graceful RPC shutdown.
        method = ""
        try:
            client = PEKClient(state.socket_path, timeout_seconds=5.0)
            await asyncio.to_thread(client.shutdown, 5.0)
            method = "rpc"
            logger.info("PEK daemon: sent shutdown RPC to pid=%d", state.pid)
        except DaemonError as e:
            logger.warning(
                "PEK shutdown RPC failed (%s) — falling back to SIGTERM", e,
            )

        # 2. Wait for the process to actually exit.
        if await asyncio.to_thread(self._wait_dead, state.pid, grace):
            clear_state(state_dir)
            return {
                "stopped": True,
                "method": method or "rpc",
                "pid": state.pid,
            }

        # 3. SIGTERM fallback.
        logger.warning("PEK daemon pid=%d still alive after %.1fs — SIGTERM",
                       state.pid, grace)
        self._kill(state.pid, signal.SIGTERM)
        if await asyncio.to_thread(self._wait_dead, state.pid, DEFAULT_KILL_GRACE_SECONDS):
            clear_state(state_dir)
            return {"stopped": True, "method": "sigterm", "pid": state.pid}

        # 4. SIGKILL last resort.
        logger.warning("PEK daemon pid=%d ignored SIGTERM — SIGKILL", state.pid)
        self._kill(state.pid, signal.SIGKILL)
        await asyncio.to_thread(self._wait_dead, state.pid, DEFAULT_KILL_GRACE_SECONDS)
        clear_state(state_dir)
        return {"stopped": not is_pid_alive(state.pid),
                "method": "sigkill", "pid": state.pid}

    @staticmethod
    def _wait_dead(pid: int, timeout_seconds: float) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not is_pid_alive(pid):
                return True
            time.sleep(0.2)
        return not is_pid_alive(pid)

    @staticmethod
    def _kill(pid: int, sig: int) -> None:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass
        except PermissionError:
            logger.error(
                "Cannot signal pid=%d (EPERM); daemon may be owned by another user",
                pid,
            )

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        self._reporter.emit_output(
            AgentOutput(
                display_type="metrics",
                title="PEK Daemon Stopped",
                content=(
                    f"pid={result.get('pid')} via {result.get('method')} "
                    f"(stopped={result.get('stopped')})"
                ),
                data=result,
            )
        )
        return None
