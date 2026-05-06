"""Persistent state for the PEK daemon.

Single source of truth: ``<state_dir>/state.json``. Every adapter
(``pek_start`` / ``pek_parse`` / ``pek_stop``) reads and updates this
file. The daemon also writes its own ``status`` field as it transitions
through ``starting`` → ``ready`` → ``shutting_down``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


STATE_FILENAME = "state.json"
SOCKET_FILENAME = "pek.sock"
LOG_FILENAME = "daemon.log"


@dataclass
class DaemonState:
    pid: int
    socket_path: str
    started_at: str
    device: str
    config_path: str
    status: str = "starting"   # starting | ready | shutting_down
    last_error: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def state_path(state_dir: str | os.PathLike) -> Path:
    return Path(state_dir) / STATE_FILENAME


def default_socket_path(state_dir: str | os.PathLike) -> Path:
    return Path(state_dir) / SOCKET_FILENAME


def default_log_path(state_dir: str | os.PathLike) -> Path:
    return Path(state_dir) / LOG_FILENAME


def write_state(state_dir: str | os.PathLike, state: DaemonState) -> None:
    p = state_path(state_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
    os.replace(tmp, p)   # atomic on POSIX


def read_state(state_dir: str | os.PathLike) -> Optional[DaemonState]:
    p = state_path(state_dir)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return DaemonState(**data)
    except Exception:
        return None


def clear_state(state_dir: str | os.PathLike) -> None:
    p = state_path(state_dir)
    if p.is_file():
        try:
            p.unlink()
        except OSError:
            pass


def is_pid_alive(pid: int) -> bool:
    """POSIX-only liveness check via ``kill(pid, 0)``.

    Returns False for pid <= 0, EPERM means alive but not ours, ESRCH
    means dead.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
