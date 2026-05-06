"""Writer for artifacts.db — the unified artifact store.

Replaces the previous ExperimentPaperWriter / EvaluationsWriter /
PaperWritingWriter trio with a single API around four tables:
sessions, artifacts, artifact_metrics, artifact_links.

Design intent: agent producers should think in terms of "I'm emitting an
artifact of type X (optionally linked to a session/parent), with these
metrics", rather than picking which of N domain-specific tables fits.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.db.base import BaseDatabase
from src.db.schemas.artifacts_schema import ARTIFACTS_DDL


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _payload(blob: Optional[Dict[str, Any]]) -> str:
    return json.dumps(blob or {}, ensure_ascii=False)


class ArtifactsWriter(BaseDatabase):
    def __init__(self, db_path: str = "output/artifacts.db"):
        super().__init__(db_path)
        self.init_schema(ARTIFACTS_DDL)

    # ── sessions ────────────────────────────────────────────
    def upsert_session(
        self,
        session_id: str = "",
        pipeline_name: str = "",
        idea_id: str = "",
        status: str = "running",
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not session_id:
            session_id = _new_id()
        self.execute(
            """INSERT INTO sessions (session_id, pipeline_name, idea_id, status, payload_json)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                 pipeline_name = excluded.pipeline_name,
                 idea_id       = COALESCE(NULLIF(excluded.idea_id, ''), sessions.idea_id),
                 status        = excluded.status,
                 payload_json  = excluded.payload_json""",
            (session_id, pipeline_name, idea_id, status, _payload(payload)),
        )
        self.commit()
        return session_id

    def finish_session(self, session_id: str, status: str = "completed") -> None:
        self.execute(
            """UPDATE sessions
                  SET status = ?, finished_at = datetime('now')
                WHERE session_id = ?""",
            (status, session_id),
        )
        self.commit()

    # ── artifacts ────────────────────────────────────────────
    def upsert_artifact(
        self,
        artifact_id: str = "",
        artifact_type: str = "other",
        idea_id: str = "",
        session_id: str = "",
        parent_id: str = "",
        status: str = "created",
        role: str = "",
        file_path: str = "",
        file_size_bytes: int = 0,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Insert or update an artifact.

        Deduplication: if (session_id, file_path) already exists with a
        non-empty file_path, reuse the existing artifact_id rather than
        creating a duplicate row.
        """
        if session_id and file_path:
            existing = self.fetchone(
                "SELECT artifact_id FROM artifacts WHERE session_id = ? AND file_path = ?",
                (session_id, file_path),
            )
            if existing:
                artifact_id = existing["artifact_id"]
                self.execute(
                    """UPDATE artifacts
                          SET artifact_type   = ?,
                              idea_id         = COALESCE(NULLIF(?, ''), idea_id),
                              parent_id       = COALESCE(NULLIF(?, ''), parent_id),
                              status          = ?,
                              role            = ?,
                              file_size_bytes = ?,
                              payload_json    = ?,
                              updated_at      = datetime('now')
                        WHERE artifact_id = ?""",
                    (
                        artifact_type, idea_id, parent_id, status, role,
                        file_size_bytes, _payload(payload), artifact_id,
                    ),
                )
                self.commit()
                return artifact_id

        if not artifact_id:
            artifact_id = _new_id()

        self.execute(
            """INSERT INTO artifacts
                 (artifact_id, artifact_type, idea_id, session_id, parent_id,
                  status, role, file_path, file_size_bytes, payload_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(artifact_id) DO UPDATE SET
                 artifact_type   = excluded.artifact_type,
                 status          = excluded.status,
                 role            = excluded.role,
                 file_size_bytes = excluded.file_size_bytes,
                 payload_json    = excluded.payload_json,
                 updated_at      = datetime('now')""",
            (
                artifact_id, artifact_type, idea_id,
                session_id or None, parent_id or None,
                status, role, file_path, file_size_bytes, _payload(payload),
            ),
        )
        self.commit()
        return artifact_id

    def update_artifact_status(
        self,
        artifact_id: str,
        status: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        if payload is None:
            self.execute(
                """UPDATE artifacts
                      SET status = ?, updated_at = datetime('now')
                    WHERE artifact_id = ?""",
                (status, artifact_id),
            )
        else:
            self.execute(
                """UPDATE artifacts
                      SET status       = ?,
                          payload_json = ?,
                          updated_at   = datetime('now')
                    WHERE artifact_id = ?""",
                (status, _payload(payload), artifact_id),
            )
        self.commit()

    # ── metrics ─────────────────────────────────────────────
    def insert_metric(
        self,
        artifact_id: str,
        metric_name: str,
        metric_value: float,
        is_primary: bool = False,
    ) -> None:
        self.execute(
            """INSERT INTO artifact_metrics
                 (artifact_id, metric_name, metric_value, is_primary)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(artifact_id, metric_name) DO UPDATE SET
                 metric_value = excluded.metric_value,
                 is_primary   = excluded.is_primary""",
            (artifact_id, metric_name, float(metric_value), 1 if is_primary else 0),
        )
        self.commit()

    def insert_metrics_from_dict(
        self,
        artifact_id: str,
        metrics: Dict[str, Any],
        primary_name: str = "",
    ) -> int:
        """Insert numeric metrics from a flat dict.

        Non-numeric values are silently ignored — they belong in payload_json,
        not in the metrics table (which exists specifically for sortable
        comparisons).
        """
        rows: List[Tuple[Any, ...]] = []
        for name, raw in (metrics or {}).items():
            if isinstance(raw, bool):
                value = 1.0 if raw else 0.0
            elif isinstance(raw, (int, float)):
                value = float(raw)
            else:
                continue
            rows.append((
                artifact_id, name, value,
                1 if name == primary_name else 0,
            ))
        if not rows:
            return 0
        self.executemany(
            """INSERT INTO artifact_metrics
                 (artifact_id, metric_name, metric_value, is_primary)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(artifact_id, metric_name) DO UPDATE SET
                 metric_value = excluded.metric_value,
                 is_primary   = excluded.is_primary""",
            rows,
        )
        self.commit()
        return len(rows)

    # ── links ───────────────────────────────────────────────
    def insert_link(
        self,
        from_id: str,
        to_id: str,
        link_kind: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.execute(
            """INSERT INTO artifact_links (from_id, to_id, link_kind, payload_json)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(from_id, to_id, link_kind) DO UPDATE SET
                 payload_json = excluded.payload_json""",
            (from_id, to_id, link_kind, _payload(payload)),
        )
        self.commit()
