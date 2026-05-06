"""Parse one PDF through a running PEK daemon.

Connects to the daemon via Unix socket, ships the parse request, and
returns a single-element ``parsed_papers`` list shaped identically to
``pdf_kit_parse``'s output so downstream gates / persisters work
unchanged.

If the daemon is unreachable this module raises (per design choice A):
no auto-restart, the failure surfaces to the pipeline gate.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseModule
from ..monitoring.reporter import AgentOutput

from src.pdf_parser.daemon.client import DaemonError, PEKClient
from src.pdf_parser.daemon.state import is_pid_alive, read_state

logger = logging.getLogger(__name__)


DEFAULT_STATE_DIR = "output/pek_daemon"
DEFAULT_PARSE_TIMEOUT_SECONDS = 600.0


class PEKParseModule(BaseModule):
    module_name = "pek_parse"

    INPUT_SPEC = {
        "pdf_path": {"type": "str", "required": False, "default": ""},
        "pdf_files": {"type": "list", "required": False, "default": []},
        "output_dir": {"type": "str", "required": False, "default": ""},
        "socket_path": {"type": "str", "required": False, "default": ""},
        "state_dir": {"type": "str", "required": False, "default": ""},
        "timeout_seconds": {"type": "float", "required": False, "default": 0.0},
    }
    OUTPUT_SPEC = {
        "parsed_papers": {"type": "list"},
        "parse_errors": {"type": "list"},
        "stats": {"type": "dict"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        pdf_path = self._resolve_pdf(inputs)
        if not pdf_path:
            return {
                "parsed_papers": [],
                "parse_errors": [],
                "stats": {"total": 0, "parsed": 0, "failed": 0},
            }

        socket_path = self._resolve_socket(inputs)
        timeout_seconds = float(
            inputs.get("timeout_seconds")
            or self.config.get("timeout_seconds")
            or DEFAULT_PARSE_TIMEOUT_SECONDS
        )

        output_dir = self._resolve_output_dir(inputs, pdf_path)

        client = PEKClient(socket_path, timeout_seconds=timeout_seconds)

        if self.has_progress_reporter:
            self._reporter.emit("parsing", file=Path(pdf_path).stem)

        try:
            result = await asyncio.to_thread(client.parse, pdf_path, output_dir)
        except DaemonError as e:
            logger.error("PEK daemon parse failed for %s: %s", pdf_path, e)
            return {
                "parsed_papers": [],
                "parse_errors": [{"file": pdf_path, "error": str(e),
                                  "error_type": e.error_type}],
                "stats": {"total": 1, "parsed": 0, "failed": 1},
            }
        except (TimeoutError, OSError) as e:
            # Includes socket.timeout (TimeoutError on Py3.10+) when the
            # daemon RPC exceeds timeout_seconds. Surface as a graceful
            # parse failure so the pipeline can skip this PDF and move
            # on instead of crashing the whole layer.
            logger.error(
                "PEK daemon RPC error for %s: %s (%s)", pdf_path, e, type(e).__name__,
            )
            return {
                "parsed_papers": [],
                "parse_errors": [{
                    "file": pdf_path,
                    "error": str(e) or repr(e),
                    "error_type": type(e).__name__,
                }],
                "stats": {"total": 1, "parsed": 0, "failed": 1},
            }

        return {
            "parsed_papers": [result],
            "parse_errors": [],
            "stats": {
                "total": 1,
                "parsed": 1,
                "failed": 0,
                "elapsed_seconds": (result.get("parse_time_ms", 0) or 0) / 1000.0,
            },
        }

    # ------------------------------------------------------------------
    # Resolvers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_pdf(inputs: Dict[str, Any]) -> str:
        pdf_path = inputs.get("pdf_path") or ""
        if pdf_path:
            return str(pdf_path)
        files = inputs.get("pdf_files") or []
        if files:
            return str(files[0])
        return ""

    def _resolve_socket(self, inputs: Dict[str, Any]) -> str:
        sp = inputs.get("socket_path") or self.config.get("socket_path") or ""
        if sp:
            return str(sp)

        state_dir = (
            inputs.get("state_dir")
            or self.config.get("state_dir")
            or DEFAULT_STATE_DIR
        )
        state = read_state(state_dir)
        if state is None:
            raise FileNotFoundError(
                f"No PEK daemon state at {state_dir}/state.json — call "
                f"pek_start first or pass socket_path explicitly"
            )
        if not is_pid_alive(state.pid):
            raise RuntimeError(
                f"PEK daemon pid={state.pid} is not alive; restart with pek_start"
            )
        return state.socket_path

    def _resolve_output_dir(self, inputs: Dict[str, Any], pdf_path: str) -> str:
        out = inputs.get("output_dir") or self.config.get("output_dir") or ""
        if not out:
            raise ValueError("pek_parse requires output_dir (per-PDF or per-batch)")
        # If output_dir already names a leaf folder for this PDF use it as
        # is; otherwise auto-create a stem subdir, mirroring pdf_kit_parse.
        if str(out).rstrip("/").endswith(Path(pdf_path).stem):
            save_dir = str(out)
        else:
            save_dir = os.path.join(str(out), Path(pdf_path).stem)
        os.makedirs(save_dir, exist_ok=True)
        return save_dir

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        stats = result.get("stats", {})
        self._reporter.emit_output(
            AgentOutput(
                display_type="metrics",
                title="PEK Parse",
                content=(
                    f"{stats.get('parsed', 0)}/{stats.get('total', 0)} parsed "
                    f"in {stats.get('elapsed_seconds', 0):.1f}s"
                ),
                data=stats,
            )
        )
        return None
