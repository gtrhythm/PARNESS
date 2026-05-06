"""paper_intra_index_incremental — refresh one paper's index when its
papers.db content has drifted.

The whole-paper indexing strategy means there are no per-section nodes
to diff individually. Detection is at the *paper* granularity:

* compute the content_hash over the full ordered concatenation of
  ``section_text`` (matching ``_paper_text_hash`` from the main module),
* look up the paper's existing :Provenance node — its ``paper_text_hash``
  property carries the hash of the snapshot we last indexed,
* if the hash matches → skip everything (no LLM, no writes),
* otherwise → wipe the previous unit / element nodes for this paper
  and re-run the full ``paper_intra_index`` pass.

This adapter never opens sqlite — it delegates that to
``paper_db_reader``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import BaseModule
from .paper_db_reader import PaperDBReaderModule
from .paper_intra_index import PaperIntraIndexModule, _paper_text_hash
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class PaperIntraIndexIncrementalModule(BaseModule):
    """Refresh a paper's intra-paper index after upstream content changes."""

    module_name = "paper_intra_index_incremental"

    INPUT_SPEC = {
        "paper_id": {"type": "str", "required": True},
        "db_path": {"type": "str", "required": False, "default": ""},
        "force": {"type": "bool", "required": False, "default": False},
    }
    OUTPUT_SPEC = {
        "paper_id": {"type": "str"},
        "drift": {"type": "bool"},
        "skipped": {"type": "bool"},
        "previous_text_hash": {"type": "str"},
        "current_text_hash": {"type": "str"},
        "reindex_result": {"type": "dict"},
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.store import KGStore

        paper_id = str(inputs["paper_id"])
        db_path = inputs.get("db_path") or self.config.get("db_path") or ""
        force = bool(inputs.get("force", False))

        empty: Dict[str, Any] = {
            "paper_id": paper_id,
            "drift": False,
            "skipped": True,
            "previous_text_hash": "",
            "current_text_hash": "",
            "reindex_result": {},
        }

        # 1. Pull the current bundle (read-only).
        reader = PaperDBReaderModule(self.config.get("paper_db_reader") or {})
        bundle = await reader.execute({"paper_id": paper_id, "db_path": db_path})
        if not bundle.get("found"):
            empty["skipped"] = True
            return empty

        sections = bundle["sections"]
        current_hash = _paper_text_hash(sections)

        # 2. Look up the paper provenance for the previously indexed hash.
        previous_hash = ""
        store = KGStore(config=self.config.get("neo4j"))
        try:
            with store._session() as s:
                rec = s.run(
                    "MATCH (p:Provenance {id: $pid}) RETURN p.paper_text_hash AS h",
                    pid=f"paper_{paper_id}",
                ).single()
            if rec is not None:
                previous_hash = rec["h"] or ""
        finally:
            store.close()

        if not force and previous_hash == current_hash and previous_hash:
            return {
                "paper_id": paper_id,
                "drift": False,
                "skipped": True,
                "previous_text_hash": previous_hash,
                "current_text_hash": current_hash,
                "reindex_result": {},
            }

        # 3. Drift detected → wipe old paper data and re-index.
        store = KGStore(config=self.config.get("neo4j"))
        try:
            for src_type in (
                "paper_unit", "paper_table", "paper_formula", "paper_image",
                "paper_section",
            ):
                try:
                    store.delete_source(src_type, paper_id)
                except Exception as exc:
                    logger.debug("delete_source(%s, %s) failed: %s",
                                 src_type, paper_id, exc)
        finally:
            store.close()

        indexer = PaperIntraIndexModule(self.config)
        reindex_result = await indexer.execute({
            "paper_id": paper_id,
            "paper_meta": bundle["paper_meta"],
            "sections": sections,
            "tables": bundle.get("tables") or [],
            "formulas": bundle.get("formulas") or [],
            "images": bundle.get("images") or [],
        })

        # 4. Stamp the snapshot hash on the paper provenance so the next
        #    incremental run can short-circuit.
        store = KGStore(config=self.config.get("neo4j"))
        try:
            with store._session() as s:
                s.run(
                    "MERGE (p:Provenance {id: $pid}) "
                    "SET p.paper_text_hash = $h, p.entity_type = 'paper', "
                    "    p.entity_id = $paper_id",
                    pid=f"paper_{paper_id}",
                    h=current_hash,
                    paper_id=paper_id,
                )
        finally:
            store.close()

        return {
            "paper_id": paper_id,
            "drift": True,
            "skipped": False,
            "previous_text_hash": previous_hash,
            "current_text_hash": current_hash,
            "reindex_result": reindex_result,
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        return AgentOutput(
            display_type="metrics",
            title="Paper Intra Index (Incremental)",
            content=(
                f"paper_id={result.get('paper_id')} "
                f"drift={result.get('drift')} "
                f"skipped={result.get('skipped')}"
            ),
            data={
                "paper_id": result.get("paper_id"),
                "drift": result.get("drift", False),
            },
        )
