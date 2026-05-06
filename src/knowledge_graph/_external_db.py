"""Read-only access to external SQLite databases owned by other processes.

The KG ingestion pipeline reads from `output/papers.db` and
`output/knowledge_store/knowledge_store.db`, both of which are written by
external processes. This module is the *only* sanctioned way to open them:
it forces SQLite URI `mode=ro`, autocommit (no transactions), and short-lived
connections so we never block writers or accidentally write.

See docs/knowledge_graph_design/ingestion_and_edge_discovery_design.md §11.5.
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path
from typing import Iterator


EXTERNAL_DB_PATHS: dict[str, str] = {
    "papers": "output/papers.db",
    "knowledge_store": "output/knowledge_store/knowledge_store.db",
}


def _resolve(name_or_path: str) -> str:
    if name_or_path in EXTERNAL_DB_PATHS:
        return EXTERNAL_DB_PATHS[name_or_path]
    return name_or_path


@contextlib.contextmanager
def open_readonly(
    name_or_path: str,
    *,
    timeout: float = 5.0,
) -> Iterator[sqlite3.Connection]:
    """Open a known external SQLite DB read-only.

    `name_or_path` may be a registry key (e.g. ``"papers"``) or a literal
    filesystem path (used by tests or by callers that already resolved the
    path from config).

    The returned connection has ``isolation_level=None`` (autocommit) and
    ``row_factory=sqlite3.Row``. Any ``INSERT``/``UPDATE``/``DELETE``/``CREATE``
    will raise because the underlying file handle is opened with ``mode=ro``.
    """
    path = _resolve(name_or_path)
    if not Path(path).exists():
        raise FileNotFoundError(f"external DB not found: {path}")
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=timeout, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
