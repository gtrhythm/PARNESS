"""paper_db_reader — read all units of one paper from papers.db.

This adapter is the *only* place in the intra-paper indexing path that
touches papers.db. It is read-only (uses
:func:`src.knowledge_graph._external_db.open_readonly`), and emits a
plain-dict ``PaperBundle`` that downstream KG agents consume — they never
open sqlite themselves.

See docs/knowledge_graph_design/ingestion_and_edge_discovery_design.md
on the DB / KG decoupling.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.knowledge_graph._external_db import open_readonly
from .base import BaseModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


def _row_dict(row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}


class PaperDBReaderModule(BaseModule):
    """Materialize one paper's full structural inventory from papers.db.

    Output keys
    -----------
    paper_meta : Dict
        Row from ``papers`` (or ``{}`` if the paper id has section data but
        no header row — rare but possible).
    sections : List[Dict]
        Ordered by ``section_order`` ascending. Each row has its raw
        columns (``section_text``, ``section_title``, ``section_type``,
        ``page_number``, ``section_order``, ``id``).
    tables / formulas / images : List[Dict]
        Companions, ordered by ``*_order``. Filtered to ``paper_id``.
    found : bool
        True iff at least one of (paper row, section row) exists.
    """

    module_name = "paper_db_reader"

    INPUT_SPEC = {
        "paper_id": {"type": "str", "required": True},
        "db_path": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "paper_id": {"type": "str"},
        "paper_meta": {"type": "dict"},
        "sections": {"type": "list"},
        "tables": {"type": "list"},
        "formulas": {"type": "list"},
        "images": {"type": "list"},
        "found": {"type": "bool"},
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        paper_id = inputs["paper_id"]
        db_path = inputs.get("db_path") or self.config.get("db_path") or "papers"

        empty: Dict[str, Any] = {
            "paper_id": paper_id,
            "paper_meta": {},
            "sections": [],
            "tables": [],
            "formulas": [],
            "images": [],
            "found": False,
        }

        try:
            with open_readonly(db_path) as conn:
                paper_row = conn.execute(
                    "SELECT * FROM papers WHERE paper_id = ?",
                    (paper_id,),
                ).fetchone()

                section_rows = conn.execute(
                    "SELECT * FROM paper_sections "
                    "WHERE paper_id = ? ORDER BY section_order",
                    (paper_id,),
                ).fetchall()

                table_rows = self._fetch_optional(
                    conn,
                    "SELECT * FROM paper_tables WHERE paper_id = ? "
                    "ORDER BY table_order",
                    (paper_id,),
                )
                formula_rows = self._fetch_optional(
                    conn,
                    "SELECT * FROM paper_formulas WHERE paper_id = ? "
                    "ORDER BY formula_order",
                    (paper_id,),
                )
                image_rows = self._fetch_optional(
                    conn,
                    "SELECT * FROM paper_images WHERE paper_id = ? "
                    "ORDER BY image_order",
                    (paper_id,),
                )
        except FileNotFoundError:
            logger.warning("paper_db_reader: papers.db not found at %s", db_path)
            return empty

        sections = [_row_dict(r) for r in section_rows]
        if paper_row is None and not sections:
            logger.info("paper_db_reader: no rows for paper_id=%s", paper_id)
            return empty

        return {
            "paper_id": paper_id,
            "paper_meta": _row_dict(paper_row) if paper_row else {},
            "sections": sections,
            "tables": [_row_dict(r) for r in table_rows],
            "formulas": [_row_dict(r) for r in formula_rows],
            "images": [_row_dict(r) for r in image_rows],
            "found": True,
        }

    @staticmethod
    def _fetch_optional(conn, sql: str, params: tuple) -> List[Any]:
        import sqlite3
        try:
            return conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            logger.debug("paper_db_reader optional table missing: %s", exc)
            return []

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        return AgentOutput(
            display_type="metrics",
            title="Paper DB Reader",
            content=(
                f"paper_id={result.get('paper_id')} "
                f"sections={len(result.get('sections', []))} "
                f"tables={len(result.get('tables', []))} "
                f"formulas={len(result.get('formulas', []))} "
                f"images={len(result.get('images', []))}"
            ),
            data={
                "paper_id": result.get("paper_id"),
                "section_count": len(result.get("sections", [])),
                "found": result.get("found", False),
            },
        )
