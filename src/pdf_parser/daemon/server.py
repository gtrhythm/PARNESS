"""PEK daemon server.

Loads ``PDFExtractKitEngine`` once, then serves parse requests over a
Unix domain socket forever. Strictly serial — one client at a time —
because the underlying PEK models share GPU state.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .protocol import (
    CMD_PARSE,
    CMD_PING,
    CMD_SHUTDOWN,
    recv_message,
    send_message,
)
from .state import (
    DaemonState,
    clear_state,
    default_socket_path,
    read_state,
    write_state,
)


logger = logging.getLogger(__name__)


class PEKDaemon:
    def __init__(
        self,
        state_dir: str,
        socket_path: Optional[str] = None,
        device: Optional[str] = None,
        config_path: Optional[str] = None,
    ):
        self._state_dir = Path(state_dir)
        self._socket_path = Path(socket_path) if socket_path else default_socket_path(state_dir)
        self._device = device
        self._config_path = config_path
        self._engine = None
        self._server_sock: Optional[socket.socket] = None
        self._shutdown_event = threading.Event()
        self._state: Optional[DaemonState] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run(self) -> int:
        self._state_dir.mkdir(parents=True, exist_ok=True)

        if self._socket_path.exists():
            try:
                self._socket_path.unlink()
            except OSError as e:
                logger.error("Failed to remove stale socket %s: %s",
                             self._socket_path, e)
                return 2

        self._write_initial_state()
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        try:
            self._load_engine()
        except Exception as e:
            logger.exception("Engine init failed")
            self._update_state(status="failed", last_error=str(e))
            return 3

        try:
            self._open_socket()
        except Exception as e:
            logger.exception("Socket bind failed")
            self._update_state(status="failed", last_error=str(e))
            self._teardown_engine()
            return 4

        self._update_state(status="ready")
        logger.info("PEKDaemon ready: pid=%d socket=%s device=%s",
                    os.getpid(), self._socket_path, self._device)

        exit_code = 0
        try:
            self._serve_forever()
        except Exception:
            logger.exception("Serve loop crashed")
            exit_code = 5
        finally:
            self._update_state(status="shutting_down")
            self._teardown_socket()
            self._teardown_engine()
            clear_state(self._state_dir)
            logger.info("PEKDaemon exited cleanly")

        return exit_code

    def _handle_signal(self, signum, _frame):
        logger.info("Received signal %d, shutting down", signum)
        self._shutdown_event.set()
        # Unblock accept() — best-effort; we connect to ourselves so the
        # server socket wakes up from the blocking accept call.
        self._poke_self()

    def _poke_self(self) -> None:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(str(self._socket_path))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Engine
    # ------------------------------------------------------------------

    def _load_engine(self):
        from src.pdf_parser.engines.pdf_extract_kit_engine import PDFExtractKitEngine
        engine = PDFExtractKitEngine(
            config_path=self._config_path,
            device=self._device,
        )
        engine._initialize()
        self._engine = engine
        # Sync the device that engine actually picked
        self._device = engine._device

    def _teardown_engine(self):
        if self._engine is not None:
            try:
                self._engine.close()
            except Exception:
                logger.exception("engine.close() failed")
            self._engine = None

    # ------------------------------------------------------------------
    # Socket loop
    # ------------------------------------------------------------------

    def _open_socket(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(self._socket_path))
        os.chmod(str(self._socket_path), 0o600)
        sock.listen(8)
        self._server_sock = sock

    def _teardown_socket(self):
        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None
        if self._socket_path.exists():
            try:
                self._socket_path.unlink()
            except OSError:
                pass

    def _serve_forever(self):
        assert self._server_sock is not None
        while not self._shutdown_event.is_set():
            try:
                client_sock, _ = self._server_sock.accept()
            except OSError:
                if self._shutdown_event.is_set():
                    break
                raise
            if self._shutdown_event.is_set():
                client_sock.close()
                break
            try:
                self._handle_client(client_sock)
            finally:
                try:
                    client_sock.close()
                except OSError:
                    pass

    def _handle_client(self, client_sock: socket.socket):
        try:
            request = recv_message(client_sock)
        except Exception as e:
            logger.warning("Failed to read request: %s", e)
            return

        cmd = request.get("cmd", "")
        try:
            if cmd == CMD_PING:
                send_message(client_sock, {"ok": True, "result": {"pid": os.getpid()}})
            elif cmd == CMD_PARSE:
                result = self._do_parse(request)
                send_message(client_sock, {"ok": True, "result": result})
            elif cmd == CMD_SHUTDOWN:
                send_message(client_sock, {"ok": True, "result": {"shutdown": True}})
                self._shutdown_event.set()
            else:
                send_message(client_sock, {
                    "ok": False,
                    "error": f"unknown cmd: {cmd!r}",
                    "error_type": "ValueError",
                })
        except Exception as e:
            logger.exception("cmd %s failed", cmd)
            try:
                send_message(client_sock, {
                    "ok": False,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                })
            except Exception:
                pass

    def _do_parse(self, request: Dict[str, Any]) -> Dict[str, Any]:
        pdf_path = request.get("pdf_path", "")
        output_dir = request.get("output_dir", "")
        if not pdf_path or not output_dir:
            raise ValueError("parse requires pdf_path and output_dir")
        if not os.path.isfile(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        assert self._engine is not None
        os.makedirs(output_dir, exist_ok=True)
        t0 = time.time()
        self._engine.parse_to_output_dir(pdf_path, output_dir)
        parse_ms = int((time.time() - t0) * 1000)

        from src.pdf_parser.result_extractor import extract_structured_result
        parsed = extract_structured_result(pdf_path, output_dir)
        parsed["parse_time_ms"] = parse_ms
        return parsed

    # ------------------------------------------------------------------
    # State file
    # ------------------------------------------------------------------

    def _write_initial_state(self):
        existing = read_state(self._state_dir)
        # In the rare race where another daemon raced us to the same
        # state_dir, we'd overwrite it — pek_start prevents this by
        # checking liveness before forking, so by the time we get here
        # we're authoritative.
        self._state = DaemonState(
            pid=os.getpid(),
            socket_path=str(self._socket_path),
            started_at=datetime.now(timezone.utc).isoformat(),
            device=self._device or "auto",
            config_path=self._config_path or "",
            status="starting",
        )
        if existing is not None:
            self._state.extra = {"replaced_pid": existing.pid}
        write_state(self._state_dir, self._state)

    def _update_state(self, **changes):
        if self._state is None:
            return
        for k, v in changes.items():
            setattr(self._state, k, v)
        write_state(self._state_dir, self._state)


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="pek-daemon")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--socket-path", default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    daemon = PEKDaemon(
        state_dir=args.state_dir,
        socket_path=args.socket_path,
        device=args.device,
        config_path=args.config,
    )
    return daemon.run()


if __name__ == "__main__":
    sys.exit(main())
