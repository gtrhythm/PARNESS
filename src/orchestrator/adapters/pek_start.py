"""Start the PEK daemon (or attach to a running one).

The current orchestrator runs each node in a fresh subprocess that
``os._exit(0)``s on completion, so models loaded in-process die with the
node. ``pek_start`` works around that by spawning a *detached* daemon
process via ``Popen(start_new_session=True)`` whose lifetime is decoupled
from the spawning subprocess.

State (pid, socket path) is persisted to ``<state_dir>/state.json`` so
``pek_parse`` and ``pek_stop`` can find the daemon later.

Behavior on existing daemon: if state.json exists AND its pid is alive
AND a ping succeeds, this module is a no-op and returns the existing
endpoint. If the pid is dead or unreachable, the stale state is
overwritten and a fresh daemon is started.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseModule
from ..monitoring.reporter import AgentOutput

from src.pdf_parser.daemon.client import DaemonError, PEKClient
from src.pdf_parser.daemon.state import (
    default_log_path,
    default_socket_path,
    is_pid_alive,
    read_state,
)

logger = logging.getLogger(__name__)


DEFAULT_STATE_DIR = "output/pek_daemon"
DEFAULT_READY_TIMEOUT_SECONDS = 300.0      # cold model load can take minutes
DEFAULT_POLL_INTERVAL_SECONDS = 1.0


class PEKStartModule(BaseModule):
    module_name = "pek_start"

    INPUT_SPEC = {
        "state_dir": {"type": "str", "required": False, "default": ""},
        "device": {"type": "str", "required": False, "default": ""},
        "config_path": {"type": "str", "required": False, "default": ""},
        "ready_timeout_seconds": {"type": "float", "required": False, "default": 0.0},
        # Optional: pin which python interpreter spawns the daemon. Defaults
        # to sys.executable. Use this to run the daemon in a dedicated env
        # (e.g. /opt/conda/envs/pek/bin/python) without changing how the
        # orchestrator itself is launched.
        "python_executable": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "socket_path": {"type": "str"},
        "pid": {"type": "int"},
        "status": {"type": "str"},
        "state_dir": {"type": "str"},
        "reused": {"type": "bool"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        state_dir = self._pick(inputs, "state_dir", DEFAULT_STATE_DIR)
        device = self._pick(inputs, "device", "") or None
        config_path = self._pick(inputs, "config_path", "") or None
        python_executable = self._pick(inputs, "python_executable", "") or None
        ready_timeout = float(
            inputs.get("ready_timeout_seconds")
            or self.config.get("ready_timeout_seconds")
            or DEFAULT_READY_TIMEOUT_SECONDS
        )

        Path(state_dir).mkdir(parents=True, exist_ok=True)

        existing = read_state(state_dir)
        if existing is not None and is_pid_alive(existing.pid):
            try:
                client = PEKClient(existing.socket_path, timeout_seconds=5.0)
                await asyncio.to_thread(client.ping, 5.0)
                logger.info(
                    "PEK daemon already running: pid=%d socket=%s — reusing",
                    existing.pid, existing.socket_path,
                )
                return {
                    "socket_path": existing.socket_path,
                    "pid": existing.pid,
                    "status": existing.status,
                    "state_dir": str(state_dir),
                    "reused": True,
                }
            except DaemonError as e:
                logger.warning(
                    "Stale state for pid=%d (ping failed: %s) — restarting",
                    existing.pid, e,
                )
        elif existing is not None:
            logger.warning(
                "Stale state for pid=%d (process not alive) — restarting",
                existing.pid,
            )

        socket_path = str(default_socket_path(state_dir))
        log_path = str(default_log_path(state_dir))

        proc = await asyncio.to_thread(
            self._spawn_daemon,
            state_dir, socket_path, device, config_path, log_path,
            python_executable,
        )

        try:
            ready_state = await asyncio.to_thread(
                self._wait_until_ready, state_dir, proc, ready_timeout,
            )
        except Exception:
            # Daemon failed to come up — best-effort kill so we don't leak it.
            self._terminate(proc)
            raise

        logger.info(
            "PEK daemon ready: pid=%d socket=%s device=%s",
            ready_state.pid, ready_state.socket_path, ready_state.device,
        )
        return {
            "socket_path": ready_state.socket_path,
            "pid": ready_state.pid,
            "status": ready_state.status,
            "state_dir": str(state_dir),
            "reused": False,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _pick(self, inputs: Dict[str, Any], key: str, default: Any) -> Any:
        v = inputs.get(key)
        if v not in (None, ""):
            return v
        v = self.config.get(key)
        if v not in (None, ""):
            return v
        return default

    @staticmethod
    def _spawn_daemon(
        state_dir: str,
        socket_path: str,
        device: Optional[str],
        config_path: Optional[str],
        log_path: str,
        python_executable: Optional[str] = None,
    ) -> subprocess.Popen:
        py = python_executable or sys.executable
        cmd = [
            py, "-m", "src.pdf_parser.daemon.server",
            "--state-dir", state_dir,
            "--socket-path", socket_path,
        ]
        if device:
            cmd += ["--device", device]
        if config_path:
            cmd += ["--config", config_path]

        log_file = open(log_path, "ab", buffering=0)

        # When pinning a different python (e.g. a conda env's interpreter),
        # prepend its sibling lib/ to LD_LIBRARY_PATH so its libstdc++ wins
        # over the system one — required when the env was built with a
        # newer toolchain than the host (e.g. CXXABI_1.3.15 from gcc 14).
        env = None
        if python_executable:
            env_root = os.path.dirname(os.path.dirname(os.path.abspath(python_executable)))
            env_lib = os.path.join(env_root, "lib")
            if os.path.isdir(env_lib):
                env = os.environ.copy()
                env["LD_LIBRARY_PATH"] = env_lib + os.pathsep + env.get("LD_LIBRARY_PATH", "")
                logger.info(
                    "PEK daemon will be spawned with python=%s, "
                    "LD_LIBRARY_PATH prefix=%s",
                    py, env_lib,
                )

        # start_new_session=True → detaches from controlling terminal and
        # creates a new process group so the daemon survives this
        # subprocess's os._exit(0).
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
            close_fds=True,
            env=env,
        )
        # We don't wait() — the daemon must outlive us. Closing our copy
        # of the log fd is safe because the child has its own.
        log_file.close()
        return proc

    @staticmethod
    def _wait_until_ready(
        state_dir: str,
        proc: subprocess.Popen,
        timeout_seconds: float,
    ):
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(
                    f"PEK daemon exited during startup (rc={proc.returncode}); "
                    f"check {default_log_path(state_dir)}"
                )
            state = read_state(state_dir)
            if state is not None and state.status == "ready":
                return state
            if state is not None and state.status == "failed":
                raise RuntimeError(
                    f"PEK daemon reported failed status: {state.last_error}"
                )
            time.sleep(DEFAULT_POLL_INTERVAL_SECONDS)
        raise TimeoutError(
            f"PEK daemon did not reach ready state within {timeout_seconds}s; "
            f"check {default_log_path(state_dir)}"
        )

    @staticmethod
    def _terminate(proc: subprocess.Popen) -> None:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        except Exception:
            pass

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        self._reporter.emit_output(
            AgentOutput(
                display_type="metrics",
                title="PEK Daemon Started",
                content=(
                    f"pid={result.get('pid')} "
                    f"socket={result.get('socket_path')} "
                    f"reused={result.get('reused')}"
                ),
                data=result,
            )
        )
        return None
