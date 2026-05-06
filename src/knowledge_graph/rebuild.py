"""Rebuild the Neo4j knowledge graph (nodes, edges, embeddings) from SQLite."""

import asyncio
import hashlib
import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from src.knowledge_graph._external_db import open_readonly

logger = logging.getLogger(__name__)

DEFAULT_DB_PATHS: Dict[str, str] = {
    "papers_db": "output/papers.db",
    "knowledge_store_db": "output/knowledge_store/knowledge_store.db",
    "paper_writing_db": "output/paper_writing.db",
}

CACHE_DIR = Path("output/knowledge_graph/extraction_cache")


class _TableSpec:
    __slots__ = (
        "source_type",
        "source_id_cols",
        "source_id_prefix",
        "prov_type",
        "prov_id_cols",
        "prov_id_prefix",
        "prov_title_col",
        "chunk_cols",
        "metadata_cols",
        "row_id_col",
    )

    def __init__(
        self,
        source_type: str,
        source_id_cols: List[str],
        source_id_prefix: str = "",
        prov_type: str = "",
        prov_id_cols: Optional[List[str]] = None,
        prov_id_prefix: str = "",
        prov_title_col: str = "",
        chunk_cols: Optional[List[str]] = None,
        metadata_cols: Optional[List[str]] = None,
        row_id_col: str = "",
    ):
        self.source_type = source_type
        self.source_id_cols = source_id_cols
        self.source_id_prefix = source_id_prefix
        self.prov_type = prov_type
        self.prov_id_cols = prov_id_cols or source_id_cols
        self.prov_id_prefix = prov_id_prefix or source_id_prefix
        self.prov_title_col = prov_title_col
        self.chunk_cols = chunk_cols or []
        self.metadata_cols = metadata_cols or []
        self.row_id_col = row_id_col

    def source_id(self, row: Dict) -> str:
        vals = "_".join(str(row.get(c, "")) for c in self.source_id_cols)
        return f"{self.source_id_prefix}{vals}" if self.source_id_prefix else vals

    def prov_id(self, row: Dict) -> str:
        vals = "_".join(str(row.get(c, "")) for c in self.prov_id_cols)
        return f"{self.prov_id_prefix}{vals}" if self.prov_id_prefix else vals

    def prov_title(self, row: Dict) -> str:
        if not self.prov_title_col:
            return ""
        val = str(row.get(self.prov_title_col, ""))
        return val[:200]

    def chunk_text(self, row: Dict) -> str:
        parts = []
        for col in self.chunk_cols:
            val = row.get(col)
            if val is not None and str(val).strip():
                parts.append(str(val).strip())
        return "\n".join(parts)

    def metadata(self, row: Dict) -> Dict[str, Any]:
        md = {}
        for col in self.metadata_cols:
            val = row.get(col)
            if val is not None:
                md[col] = val
        return md

    def row_id(self, row: Dict) -> str:
        if self.row_id_col:
            return str(row.get(self.row_id_col, ""))
        return self.source_id(row)


_PAPERS_TABLES: Dict[str, _TableSpec] = {
    "paper_sections": _TableSpec(
        source_type="paper_section",
        source_id_cols=["paper_id"],
        source_id_prefix="paper_",
        prov_type="paper",
        prov_id_cols=["paper_id"],
        prov_id_prefix="paper_",
        prov_title_col="section_title",
        chunk_cols=["content"],
        metadata_cols=["section_type", "section_order", "section_title"],
    ),
    "paper_tables": _TableSpec(
        source_type="paper_table",
        source_id_cols=["paper_id"],
        source_id_prefix="paper_",
        prov_type="paper",
        prov_id_cols=["paper_id"],
        prov_id_prefix="paper_",
        prov_title_col="caption",
        chunk_cols=["caption"],
        metadata_cols=["table_index", "caption"],
    ),
    "paper_formulas": _TableSpec(
        source_type="paper_formula",
        source_id_cols=["paper_id"],
        source_id_prefix="paper_",
        prov_type="paper",
        prov_id_cols=["paper_id"],
        prov_id_prefix="paper_",
        prov_title_col="latex_source",
        chunk_cols=["latex_source"],
        metadata_cols=["formula_index", "latex_source"],
    ),
    "paper_images": _TableSpec(
        source_type="paper_image",
        source_id_cols=["paper_id"],
        source_id_prefix="paper_",
        prov_type="paper",
        prov_id_cols=["paper_id"],
        prov_id_prefix="paper_",
        prov_title_col="caption",
        chunk_cols=["caption"],
        metadata_cols=["image_index", "caption", "file_path"],
    ),
}

_KNOWLEDGE_STORE_TABLES: Dict[str, _TableSpec] = {
    "insights": _TableSpec(
        source_type="insight",
        source_id_cols=["paper_id"],
        source_id_prefix="paper_",
        prov_type="paper",
        prov_id_cols=["paper_id"],
        prov_id_prefix="paper_",
        prov_title_col="core_insight",
        chunk_cols=["core_insight", "problem_solved", "key_trick"],
        metadata_cols=["core_insight", "problem_solved", "key_trick"],
    ),
    "insight_limitations": _TableSpec(
        source_type="insight",
        source_id_cols=["paper_id"],
        source_id_prefix="paper_",
        prov_type="paper",
        prov_id_cols=["paper_id"],
        prov_id_prefix="paper_",
        chunk_cols=["limitation"],
        metadata_cols=["limitation"],
    ),
    "insight_open_questions": _TableSpec(
        source_type="insight",
        source_id_cols=["paper_id"],
        source_id_prefix="paper_",
        prov_type="paper",
        prov_id_cols=["paper_id"],
        prov_id_prefix="paper_",
        chunk_cols=["question"],
        metadata_cols=["question"],
    ),
    "insight_reusable_components": _TableSpec(
        source_type="insight",
        source_id_cols=["paper_id"],
        source_id_prefix="paper_",
        prov_type="paper",
        prov_id_cols=["paper_id"],
        prov_id_prefix="paper_",
        chunk_cols=["component"],
        metadata_cols=["component"],
    ),
    "ideas": _TableSpec(
        source_type="idea",
        source_id_cols=["id"],
        source_id_prefix="idea_",
        prov_type="idea",
        prov_id_cols=["id"],
        prov_id_prefix="idea_",
        prov_title_col="title",
        chunk_cols=["title", "description", "methodology"],
        metadata_cols=[
            "title",
            "category",
            "novelty_score",
            "feasibility_score",
            "impact_score",
            "overall_score",
        ],
    ),
    "raw_ideas": _TableSpec(
        source_type="raw_idea",
        source_id_cols=["id"],
        source_id_prefix="raw_idea_",
        chunk_cols=["idea_text"],
        metadata_cols=["idea_text"],
    ),
    "seeds": _TableSpec(
        source_type="seed",
        source_id_cols=["id"],
        source_id_prefix="seed_",
        prov_type="seed",
        prov_id_cols=["id"],
        prov_id_prefix="seed_",
        chunk_cols=["rationale"],
        metadata_cols=["seed_type", "rationale", "cluster_id"],
    ),
    "seed_clusters": _TableSpec(
        source_type="seed_cluster",
        source_id_cols=["id"],
        source_id_prefix="cluster_",
        prov_type="seed",
        prov_id_cols=["id"],
        prov_id_prefix="seed_",
        prov_title_col="theme",
        chunk_cols=["theme"],
        metadata_cols=["theme"],
    ),
    "cross_domain_pairs": _TableSpec(
        source_type="cross_domain_pair",
        source_id_cols=["id"],
        source_id_prefix="cdp_",
        chunk_cols=["insight_a_id", "insight_b_id"],
        metadata_cols=["insight_a_id", "insight_b_id"],
    ),
    "hypotheses": _TableSpec(
        source_type="hypothesis",
        source_id_cols=["hypothesis_id"],
        source_id_prefix="hypothesis_",
        prov_type="hypothesis",
        prov_id_cols=["hypothesis_id"],
        prov_id_prefix="hypothesis_",
        prov_title_col="statement",
        chunk_cols=["statement", "testability"],
        metadata_cols=["statement", "confidence", "testability"],
    ),
    "evidence_items": _TableSpec(
        source_type="evidence",
        source_id_cols=["id"],
        source_id_prefix="evidence_",
        chunk_cols=["evidence_text"],
        metadata_cols=["stance", "strength", "hypothesis_id"],
        row_id_col="id",
    ),
    "explorations": _TableSpec(
        source_type="exploration",
        source_id_cols=["idea_id"],
        source_id_prefix="idea_",
        prov_type="idea",
        prov_id_cols=["idea_id"],
        prov_id_prefix="idea_",
        chunk_cols=["related_work", "novelty_validation"],
        metadata_cols=["related_work", "novelty_validation"],
    ),
    "critiques": _TableSpec(
        source_type="critique",
        source_id_cols=["id"],
        source_id_prefix="critique_",
        chunk_cols=["flaw"],
        metadata_cols=["flaw", "severity"],
    ),
    "theory_improvements": _TableSpec(
        source_type="theory_improvement",
        source_id_cols=["id"],
        source_id_prefix="theory_",
        chunk_cols=["theoretical_issue"],
        metadata_cols=["theoretical_issue"],
    ),
    "trends": _TableSpec(
        source_type="trend",
        source_id_cols=["id"],
        source_id_prefix="trend_",
        prov_title_col="description",
        chunk_cols=["description"],
        metadata_cols=["description"],
    ),
    "meta_gaps": _TableSpec(
        source_type="meta_gap",
        source_id_cols=["id"],
        source_id_prefix="gap_",
        chunk_cols=["gap_description"],
        metadata_cols=["gap_description"],
    ),
    "follow_up_ideas": _TableSpec(
        source_type="follow_up_idea",
        source_id_cols=["id"],
        source_id_prefix="followup_",
        chunk_cols=["future_direction"],
        metadata_cols=["original_paper_id"],
    ),
    "failure_cases": _TableSpec(
        source_type="failure_case",
        source_id_cols=["id"],
        source_id_prefix="failure_",
        chunk_cols=["failure_scenario"],
        metadata_cols=["failure_scenario"],
    ),
    "limitation_extensions": _TableSpec(
        source_type="limitation_extension",
        source_id_cols=["id"],
        source_id_prefix="limitext_",
        chunk_cols=["stated_limitation"],
        metadata_cols=["stated_limitation"],
    ),
    "transfer_ideas": _TableSpec(
        source_type="transfer_idea",
        source_id_cols=["method_name"],
        source_id_prefix="transfer_",
        chunk_cols=["source_domain", "target_domain", "method_name"],
        metadata_cols=["source_domain", "target_domain", "method_name"],
    ),
    "replication_problems": _TableSpec(
        source_type="replication_problem",
        source_id_cols=["paper_id"],
        source_id_prefix="replication_",
        chunk_cols=["issue_description"],
        metadata_cols=["issue_type"],
    ),
}

_WRITING_TABLES: Dict[str, _TableSpec] = {
    "paper_drafts": _TableSpec(
        source_type="paper_draft",
        source_id_cols=["id"],
        source_id_prefix="draft_",
        prov_type="paper_draft",
        prov_id_cols=["id"],
        prov_id_prefix="draft_",
        prov_title_col="title",
        chunk_cols=["abstract", "key_contributions"],
        metadata_cols=["title", "status", "version"],
        row_id_col="id",
    ),
    "repos": _TableSpec(
        source_type="code_repo",
        source_id_cols=["id"],
        source_id_prefix="repo_",
        prov_type="code",
        prov_id_cols=["id"],
        prov_id_prefix="repo_",
        prov_title_col="description",
        chunk_cols=["description"],
        metadata_cols=["repo_url", "description"],
        row_id_col="id",
    ),
}

_DB_TABLE_MAP: Dict[str, Dict[str, _TableSpec]] = {
    "papers_db": _PAPERS_TABLES,
    "knowledge_store_db": _KNOWLEDGE_STORE_TABLES,
    "paper_writing_db": _WRITING_TABLES,
}


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row)


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class KGRebuilder:
    def __init__(self, store, config: Optional[Dict] = None) -> None:
        self.store = store
        self.config = config or {}
        self._embedder = None
        self._chunker = None
        self._provenance = None
        self._extraction_cache: Dict[str, List[Dict]] = {}
        # (source_type, source_id) -> [node_id, ...] populated as nodes are written;
        # used by the post-ingest edge-building phases.
        self._nodes_by_source: Dict[Tuple[str, str], List[str]] = {}

    async def rebuild_all(
        self,
        llm_client,
        db_paths: Optional[Dict[str, str]] = None,
        clear_existing: bool = False,
        cache_extraction: bool = True,
    ) -> Dict[str, Any]:
        start = time.time()
        stats: Dict[str, Any] = {
            "total_nodes": 0,
            "total_edges": 0,
            "total_provenances": 0,
            "duration_seconds": 0.0,
            "errors": [],
        }

        paths = (db_paths or DEFAULT_DB_PATHS).copy()

        if clear_existing:
            await self._call(self.store.clear_all)
            await self._call(self.store.clear_vector_indexes)

        await self._call(self.store.init_schema)

        from src.knowledge_graph.embedder import get_embedder

        self._embedder = get_embedder(self.config.get("embedding"))

        from src.knowledge_graph.chunker import KGChunker
        from src.knowledge_graph.provenance import ProvenanceManager

        self._chunker = KGChunker()
        self._provenance = ProvenanceManager(self.store)
        self._nodes_by_source = {}

        if cache_extraction:
            self._load_cache()

        provenances: Set[str] = set()
        hash_to_node: Dict[str, str] = {}

        for db_key, db_path in paths.items():
            try:
                await self._process_database(
                    db_key,
                    db_path,
                    llm_client,
                    provenances,
                    hash_to_node,
                    stats,
                    cache_extraction,
                )
            except Exception as exc:
                msg = f"{db_key} ({db_path}): {exc}"
                logger.error("Failed to process database: %s", msg)
                stats["errors"].append(msg)

        await self._build_edges_for_all_sources(llm_client, paths, stats)

        try:
            stats["total_nodes"] = await self._call(self.store.get_node_count)
        except Exception:
            pass
        try:
            stats["total_edges"] = await self._call(self.store.get_edge_count)
        except Exception:
            pass
        try:
            stats["total_provenances"] = await self._call(self.store.get_provenance_count)
        except Exception:
            pass

        stats["duration_seconds"] = round(time.time() - start, 2)

        if cache_extraction:
            self._save_cache()

        logger.info(
            "Rebuild complete: %d nodes, %d edges, %d provenances in %.1fs (%d errors)",
            stats["total_nodes"],
            stats["total_edges"],
            stats["total_provenances"],
            stats["duration_seconds"],
            len(stats["errors"]),
        )
        return stats

    async def _call(self, fn, *args, **kwargs):
        result = fn(*args, **kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result

    async def _build_edges_for_all_sources(
        self,
        llm_client,
        db_paths: Dict[str, str],
        stats: Dict[str, Any],
    ) -> None:
        """Drive every per-source edge phase using the dedicated builders/walkers.

        For each (source_type, source_id) that produced new nodes we run, in
        order: internal LLM relations → structural edges → semantic edges →
        random-walk discovery → retrospect. Failures in one phase don't block
        the others; they're recorded in stats['errors'].
        """
        from src.knowledge_graph.edge_builder import KGEdgeBuilder
        from src.knowledge_graph.random_walk import KGRandomWalker

        edge_builder_cfg = dict(self.config.get("edge_builder", {}) or {})
        edge_builder_cfg.setdefault("db_paths", {
            "papers": db_paths.get("papers_db", "output/papers.db"),
            "knowledge_store": db_paths.get(
                "knowledge_store_db", "output/knowledge_store/knowledge_store.db"
            ),
        })
        builder = KGEdgeBuilder(self.store, config=edge_builder_cfg)
        walker = KGRandomWalker(self.store, config=self.config.get("random_walk"))

        for (source_type, source_id), node_ids in self._nodes_by_source.items():
            if not node_ids:
                continue
            label = f"{source_type}/{source_id}"

            # Synthesize unit dicts from persisted nodes for the LLM internal
            # relations prompt (only `id`/`text`/`type` are required by the prompt).
            units = []
            for nid in node_ids:
                node = self.store.get_node(nid)
                if not node:
                    continue
                meta = node.get("metadata", {}) or {}
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except (ValueError, TypeError):
                        meta = {}
                units.append({
                    "id": nid,
                    "node_id": nid,
                    "text": node.get("chunk_text", ""),
                    "type": meta.get("unit_type", "claim"),
                })

            for phase_name, coro in (
                ("internal_edges", builder.evaluate_internal_relations(
                    llm_client, units, source_type, source_id)),
                ("struct_edges", builder.build_structural_edges(
                    node_ids, source_type, source_id)),
                ("semantic_edges", builder.build_semantic_edges(
                    llm_client, node_ids, source_type, source_id)),
                ("random_walk", walker.discover_remote_relations(
                    llm_client, node_ids, source_type=source_type,
                    source_id=source_id)),
                ("retrospect", builder.retrospect_edges(
                    llm_client, node_ids)),
            ):
                try:
                    await coro
                except Exception as exc:
                    stats["errors"].append(f"{phase_name}[{label}]: {exc}")
                    logger.warning("Edge phase %s for %s failed: %s",
                                   phase_name, label, exc)

    async def _process_database(
        self,
        db_key: str,
        db_path: str,
        llm_client,
        provenances: Set[str],
        hash_to_node: Dict[str, str],
        stats: Dict[str, Any],
        cache_extraction: bool,
    ) -> None:
        table_map = _DB_TABLE_MAP.get(db_key)
        if not table_map:
            logger.warning("No table definitions for db_key: %s", db_key)
            return

        try:
            with open_readonly(db_path) as conn:
                for table_name, spec in table_map.items():
                    try:
                        await self._process_table(
                            conn,
                            table_name,
                            spec,
                            llm_client,
                            provenances,
                            hash_to_node,
                            stats,
                            cache_extraction,
                        )
                    except Exception as exc:
                        msg = f"{db_key}.{table_name}: {exc}"
                        logger.error("Failed to process table: %s", msg)
                        stats["errors"].append(msg)
        except FileNotFoundError:
            logger.warning("Database not found: %s", db_path)
            return

    async def _process_table(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        spec: _TableSpec,
        llm_client,
        provenances: Set[str],
        hash_to_node: Dict[str, str],
        stats: Dict[str, Any],
        cache_extraction: bool,
    ) -> None:
        try:
            cursor = conn.execute(f"SELECT * FROM [{table_name}]")
        except sqlite3.OperationalError:
            logger.info("Table %s not found, skipping", table_name)
            return

        rows = cursor.fetchall()
        if not rows:
            return

        logger.info("Processing %s: %d rows", table_name, len(rows))

        for row in rows:
            try:
                row_dict = _row_to_dict(row)
                await self._process_row(
                    row_dict,
                    spec,
                    llm_client,
                    provenances,
                    hash_to_node,
                    stats,
                    cache_extraction,
                )
            except Exception as exc:
                rid = spec.row_id(row_dict) if row_dict else "?"
                msg = f"{table_name}[{rid}]: {exc}"
                logger.error("Failed to process row: %s", msg)
                stats["errors"].append(msg)

    async def _process_row(
        self,
        row: Dict[str, Any],
        spec: _TableSpec,
        llm_client,
        provenances: Set[str],
        hash_to_node: Dict[str, str],
        stats: Dict[str, Any],
        cache_extraction: bool,
    ) -> None:
        chunk = spec.chunk_text(row)
        if not chunk or not chunk.strip():
            return

        sid = spec.source_id(row)
        md = spec.metadata(row)
        now = _now_iso()

        if spec.prov_type:
            pid = spec.prov_id(row)
            if pid not in provenances:
                self._provenance.get_or_create(
                    entity_type=spec.prov_type,
                    entity_id=pid,
                    entity_title=spec.prov_title(row),
                )
                provenances.add(pid)

        cache_key = _content_hash(f"{spec.source_type}:{chunk}")
        units = None

        if cache_extraction and cache_key in self._extraction_cache:
            units = self._extraction_cache[cache_key]
        else:
            try:
                extracted = await self._chunker.extract_units(
                    llm_client, chunk, spec.source_type, sid
                )
                units_data = [
                    {
                        "text": u.text,
                        "abstract_summary": u.abstract_summary,
                        "type": u.unit_type,
                        "evidence": u.evidence,
                    }
                    for u in extracted
                ]
                if cache_extraction:
                    self._extraction_cache[cache_key] = units_data
                units = units_data
            except Exception as exc:
                logger.warning("Extraction failed for %s, using raw text: %s", sid, exc)
                units = [
                    {
                        "text": chunk[:500],
                        "abstract_summary": "",
                        "type": "raw",
                        "evidence": "",
                    }
                ]

        for unit in units:
            text = unit.get("text", "")
            if not text or not text.strip():
                continue

            abstract = unit.get("abstract_summary", "")
            chash = _content_hash(text)

            if chash in hash_to_node:
                existing_id = hash_to_node[chash]
                if spec.prov_type:
                    pid = spec.prov_id(row)
                    try:
                        self._provenance.add_sourced_from(
                            node_id=existing_id,
                            provenance_type=spec.prov_type,
                            provenance_id=pid,
                            provenance_path=spec.source_type,
                            evidence_text=unit.get("evidence", "")[:500],
                            confidence=1.0,
                        )
                    except Exception:
                        pass
                continue

            node_id = str(uuid.uuid4())

            try:
                vector = await self._embedder.embed(text)
            except Exception as exc:
                logger.warning("Embedding failed for node %s: %s", node_id, exc)
                vector = []

            await self._call(
                self.store.create_kgnode,
                node_id,
                text,
                abstract,
                chash,
                spec.source_type,
                sid,
                md,
            )

            abstract_vector = None
            if vector and abstract:
                try:
                    abstract_vector = await self._embedder.embed(abstract)
                except Exception as exc:
                    logger.warning(
                        "Abstract embedding failed for %s: %s", node_id, exc
                    )
            if vector:
                self.store.set_node_embeddings(
                    node_id=node_id,
                    embedding=vector,
                    abstract_embedding=abstract_vector,
                )

            if spec.prov_type:
                pid = spec.prov_id(row)
                try:
                    self._provenance.add_sourced_from(
                        node_id=node_id,
                        provenance_type=spec.prov_type,
                        provenance_id=pid,
                        provenance_path=spec.source_type,
                        evidence_text=unit.get("evidence", "")[:500],
                        confidence=1.0,
                    )
                except Exception as exc:
                    logger.debug("add_sourced_from(%s -> %s) failed: %s",
                                 node_id, pid, exc)

            hash_to_node[chash] = node_id
            self._nodes_by_source.setdefault((spec.source_type, sid), []).append(node_id)

    def _cache_path(self) -> Path:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return CACHE_DIR / "extraction_cache.json"

    def _load_cache(self) -> None:
        path = self._cache_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._extraction_cache = data
                    logger.info(
                        "Loaded extraction cache: %d entries", len(data)
                    )
            except Exception as exc:
                logger.warning("Failed to load extraction cache: %s", exc)
                self._extraction_cache = {}

    def _save_cache(self) -> None:
        path = self._cache_path()
        try:
            path.write_text(
                json.dumps(self._extraction_cache, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info(
                "Saved extraction cache: %d entries",
                len(self._extraction_cache),
            )
        except Exception as exc:
            logger.warning("Failed to save extraction cache: %s", exc)
