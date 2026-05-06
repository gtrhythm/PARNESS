"""Synchronous client for the PEK daemon.

Each call opens a fresh Unix socket connection — keeps the protocol
trivial and lets multiple short-lived adapter subprocesses talk to the
same long-lived daemon without coordination.
"""

from __future__ import annotations

import socket
from typing import Any, Dict, Optional

from .protocol import (
    CMD_PARSE,
    CMD_PING,
    CMD_SHUTDOWN,
    recv_message,
    send_message,
)


class DaemonError(RuntimeError):
    """Raised when the daemon returns ``ok=false`` or the connection fails."""

    def __init__(self, message: str, error_type: str = "", traceback_str: str = ""):
        super().__init__(message)
        self.error_type = error_type
        self.traceback_str = traceback_str


class PEKClient:
    def __init__(self, socket_path: str, timeout_seconds: float = 600.0):
        self._socket_path = socket_path
        self._timeout = timeout_seconds

    # ------------------------------------------------------------------
    # Public RPCs
    # ------------------------------------------------------------------

    def ping(self, timeout_seconds: Optional[float] = 5.0) -> Dict[str, Any]:
        return self._call({"cmd": CMD_PING}, timeout=timeout_seconds)

    def parse(self, pdf_path: str, output_dir: str) -> Dict[str, Any]:
        return self._call(
            {"cmd": CMD_PARSE, "pdf_path": pdf_path, "output_dir": output_dir},
            timeout=self._timeout,
        )

    def shutdown(self, timeout_seconds: Optional[float] = 30.0) -> Dict[str, Any]:
        return self._call({"cmd": CMD_SHUTDOWN}, timeout=timeout_seconds)

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _call(self, payload: Dict[str, Any], timeout: Optional[float]) -> Dict[str, Any]:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if timeout is not None:
            sock.settimeout(timeout)
        try:
            try:
                sock.connect(self._socket_path)
            except (FileNotFoundError, ConnectionRefusedError) as e:
                raise DaemonError(
                    f"Cannot reach PEK daemon at {self._socket_path}: {e}",
                    error_type=type(e).__name__,
                ) from e
            send_message(sock, payload)
            response = recv_message(sock)
        finally:
            try:
                sock.close()
            except OSError:
                pass

        if not response.get("ok", False):
            raise DaemonError(
                response.get("error", "unknown error"),
                error_type=response.get("error_type", ""),
                traceback_str=response.get("traceback", ""),
            )
        return response.get("result", {})
