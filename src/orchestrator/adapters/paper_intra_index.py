"""paper_intra_index — whole-paper KG indexer.

Given a ``PaperBundle`` (from ``paper_db_reader``) this adapter:

    1. concatenates every ``paper_sections`` row's ``section_text`` for the
       paper into one paper-text blob, ordered by ``section_order``. The
       rows in papers.db are paragraph-fragments emitted by the PDF
       parser — *not* real sections — so treating them as discrete
       sections produced a noisy graph. The whole-paper view lets the
       LLM see the full argument structure when it extracts units.
    2. splits the blob into chunks under one third of the model's context
       window (default ~66 k tokens). Almost every paper in the corpus
       fits in a single chunk; long ones get 2-3 chunks split at
       paragraph boundaries.
    3. for each chunk runs a **single** LLM call that extracts knowledge
       units **and** the relationships among them in one shot. This
       replaces the legacy three-round chunker (which made 7+ calls per
       fragment) with one well-targeted pass.
    4. writes each unit as a ``:KGNode`` with ``source_type='paper_unit'``
       + ``:Provenance(paper_<id>)`` + an ``embedding`` so vector search
       works.
    5. wires the LLM's reported relations as ``:RELATED`` edges
       (``discovered_by='intra_paper_round1'``).
    6. wires structural ``SAME_SOURCE_PAPER`` edges pairwise across all
       intra-paper units.
    7. when more than one chunk was needed, runs round-2 cross-chunk
       stitching: for each unit, look up its top-K embedding neighbours
       within the same paper, drop pairs already connected, and ask the
       LLM about the remaining cross-chunk pairs.

Tables / formulas / images are also written as ``:KGNode`` with their
caption/content + a ``SAME_SOURCE_PAPER`` link to every unit. There are
no ``NEXT_SECTION`` / ``EXTRACTED_FROM`` / ``IN_SECTION`` edges in the
new model — the per-section structural scaffolding was meaningful only
when "section" meant a real heading.

This adapter never opens sqlite.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from .base import BaseModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal data classes
# ---------------------------------------------------------------------------


@dataclass
class _UnitRec:
    node_id: str
    text: str
    abstract_summary: str
    unit_type: str
    chunk_index: int
    paper_id: str


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


_EXTRACT_AND_RELATE_PROMPT = """\
You are reading the full text of a single research paper. Extract its \
important knowledge units AND identify the relationships among them \
in one pass.

For each unit produce:
  - id:       a short identifier ("u1", "u2", ...) UNIQUE within this reply
  - text:     a self-contained statement (under 300 chars) capturing the unit
  - type:     one of [claim, method, result, definition, observation,
              limitation, hypothesis, comparison]
  - evidence: a brief verbatim quote from the source paper (under 200 chars)

Skip table-of-contents fragments, reference list rows, and anything that \
isn't a substantive intellectual contribution.

For each meaningful relation between two units produce:
  - source_id: id of the unit doing the relating
  - target_id: id of the unit being related to
  - relation:  one of [SUPPORTS, CONTRADICTS, EXTENDS, USES_METHOD,
               BASED_ON, INSPIRED_BY, EXTRACTED_FROM]
  - confidence: 0..1
  - rationale: brief justification

Return strictly valid JSON of the form:
{{"units": [...], "relations": [...]}}

Source paper text:
---
{paper_text}
---
"""


_ROUND2_PROMPT = """\
The following pairs of knowledge units come from the same paper but were \
extracted in different chunks of the source text, so they were not \
evaluated for relationships in the first pass. Decide whether each pair \
has a meaningful relation.

Pairs:
{pairs_text}

For each related pair reply with: source_id, target_id, relation
(one of [SUPPORTS, CONTRADICTS, EXTENDS, USES_METHOD, BASED_ON,
INSPIRED_BY, RELATED_TO]), confidence (0..1), rationale. Skip
unrelated pairs.

Return JSON: {{"relations": [{{"source_id": "...", "target_id": "...",
"relation": "...", "confidence": 0.x, "rationale": "..."}}]}}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _element_node_id(paper_id: str, kind: str, element_id: Any) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{kind}:{paper_id}:{element_id}"))


def _unit_node_id(paper_id: str, content_hash: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"unit:{paper_id}:{content_hash}"))


def _concat_paper_text(sections: List[Dict[str, Any]]) -> str:
    """Ordered concat of paragraph text. Skips rows with empty
    ``section_text`` so the hash doesn't drift on whitespace-only edits."""
    parts = sorted(
        (s for s in sections if s.get("section_text")),
        key=lambda s: _safe_int(s.get("section_order")),
    )
    out: List[str] = []
    for s in parts:
        text = str(s.get("section_text") or "").strip()
        if not text:
            continue
        out.append(text)
    return "\n\n".join(out)


def _paper_text_hash(sections: List[Dict[str, Any]]) -> str:
    """Stable hash over the ordered concatenation of section_text. Same
    bytes the indexer feeds the LLM, so the incremental check can
    short-circuit when nothing drifted."""
    return _hash_text(_concat_paper_text(sections))


def _split_paper_text(paper_text: str, *, max_chars: int) -> List[str]:
    """Greedy split by paragraph boundaries so we never break mid-sentence.

    ``max_chars`` is a coarse char budget the caller derives from the
    token budget (we use 3 chars/token as a conservative ratio).
    """
    if len(paper_text) <= max_chars:
        return [paper_text]

    paragraphs = re.split(r"\n{2,}", paper_text)
    chunks: List[str] = []
    cur: List[str] = []
    cur_len = 0
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if cur and cur_len + len(para) + 2 > max_chars:
            chunks.append("\n\n".join(cur))
            cur = []
            cur_len = 0
        # Single paragraph longer than budget — hard-split on sentence ends.
        if len(para) > max_chars:
            sents = re.split(r"(?<=[.!?])\s+", para)
            buf: List[str] = []
            buf_len = 0
            for sent in sents:
                if buf and buf_len + len(sent) + 1 > max_chars:
                    chunks.append(" ".join(buf))
                    buf = []
                    buf_len = 0
                buf.append(sent)
                buf_len += len(sent) + 1
            if buf:
                if cur:
                    chunks.append("\n\n".join(cur))
                    cur = []
                    cur_len = 0
                chunks.append(" ".join(buf))
            continue
        cur.append(para)
        cur_len += len(para) + 2

    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def _strip_code_fence(text: str) -> str:
    """Drop a single leading ```lang\n ... ``` fence if present."""
    text = text.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        if nl >= 0:
            text = text[nl + 1:]
        text = text.split("```")[0]
    return text.strip()


def _isolate_json_object(text: str) -> str:
    """Return the substring from the first '{' to its balanced closer.

    The LLM sometimes wraps the JSON in narration or splits it across a
    code fence and stray text. We scan for an unescaped { and then count
    nesting (respecting string state) to find the matching }.
    """
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    # Unbalanced — fall back to the loose first..last range so the
    # later cleanup passes still get a chance.
    last = text.rfind("}")
    if last > start:
        return text[start:last + 1]
    return ""


_TRAILING_COMMA_RE = re.compile(r",(\s*[\]}])")
_SMART_QUOTE_PAIRS = (
    ("“", '"'), ("”", '"'),
    ("‘", "'"), ("’", "'"),
    ("«", '"'), ("»", '"'),
)
_PYTHON_LITERAL_RE = re.compile(r"\b(True|False|None)\b")
_PYTHON_LITERAL_MAP = {"True": "true", "False": "false", "None": "null"}


def _relax_json(text: str) -> str:
    """Apply a small set of cleanups to handle the JSON quirks MiniMax
    (and similar thinking models) tend to produce."""
    for bad, good in _SMART_QUOTE_PAIRS:
        text = text.replace(bad, good)
    text = _TRAILING_COMMA_RE.sub(r"\1", text)
    text = _PYTHON_LITERAL_RE.sub(
        lambda m: _PYTHON_LITERAL_MAP[m.group(1)],
        text,
    )
    return text


def _try_parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _parse_extract_and_relate(raw: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Parse the LLM extract+relate response.

    Strategy (most-strict-first):
        1. literal json.loads on the raw / fence-stripped text
        2. extract balanced {..} substring → json.loads
        3. apply lenient cleanups (smart quotes, trailing commas,
           Python literals) → json.loads

    Returns (units, relations). Either or both may be empty on failure.
    """
    if not raw:
        return [], []

    candidates: List[str] = []
    candidates.append(raw.strip())
    fenced = _strip_code_fence(raw)
    if fenced and fenced != candidates[0]:
        candidates.append(fenced)
    isolated = _isolate_json_object(fenced or raw)
    if isolated:
        candidates.append(isolated)
        candidates.append(_relax_json(isolated))

    obj = None
    for cand in candidates:
        if not cand:
            continue
        obj = _try_parse_json(cand)
        if isinstance(obj, dict):
            break

    if not isinstance(obj, dict):
        logger.warning(
            "paper_intra_index: failed to parse LLM JSON (raw len=%d, head=%r)",
            len(raw), raw[:200],
        )
        return [], []

    units = obj.get("units") or []
    relations = obj.get("relations") or []
    if not isinstance(units, list):
        units = []
    if not isinstance(relations, list):
        relations = []
    return units, relations


def _format_pairs_for_prompt(pairs: List[Tuple[_UnitRec, _UnitRec]]) -> str:
    parts = []
    for a, b in pairs:
        a_body = (a.abstract_summary or a.text)[:300]
        b_body = (b.abstract_summary or b.text)[:300]
        parts.append(
            f"PAIR (A={a.node_id}, B={b.node_id})\n"
            f"  A: {a_body}\n"
            f"  B: {b_body}"
        )
    return "\n\n".join(parts)


def _pair_key(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a <= b else (b, a)


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------


_DEFAULT_MIN_CONFIDENCE = 0.6
_DEFAULT_TOPK_ROUND2 = 5
_DEFAULT_PROMPT_OVERHEAD = 2_000
_CHARS_PER_TOKEN = 3   # conservative for cl100k on mixed Chinese / English


class PaperIntraIndexModule(BaseModule):
    """Whole-paper KG indexer (decoupled from sqlite)."""

    module_name = "paper_intra_index"

    INPUT_SPEC = {
        "paper_id": {"type": "str", "required": True},
        "paper_meta": {"type": "dict", "required": False, "default": {}},
        "sections": {"type": "list", "required": True},
        "tables": {"type": "list", "required": False, "default": []},
        "formulas": {"type": "list", "required": False, "default": []},
        "images": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "paper_id": {"type": "str"},
        "unit_node_ids": {"type": "list"},
        "element_node_ids": {"type": "list"},
        "chunk_count": {"type": "int"},
        "round1_unit_count": {"type": "int"},
        "round1_edge_count": {"type": "int"},
        "round2_edge_count": {"type": "int"},
        "round2_pair_count": {"type": "int"},
        "round2_skipped": {"type": "bool"},
        "same_source_edge_count": {"type": "int"},
        "errors": {"type": "list"},
        "skipped": {"type": "bool"},
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}

    # ---- main entry ---------------------------------------------------

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.store import KGStore
        from src.knowledge_graph.provenance import ProvenanceManager
        from src.knowledge_graph.embedder import get_embedder
        from src.knowledge_graph._token_budget import (
            count_tokens, llm_call_budget,
        )

        paper_id = str(inputs["paper_id"])
        sections = inputs.get("sections") or []
        tables = inputs.get("tables") or []
        formulas = inputs.get("formulas") or []
        images = inputs.get("images") or []
        paper_meta = inputs.get("paper_meta") or {}

        empty: Dict[str, Any] = {
            "paper_id": paper_id,
            "unit_node_ids": [],
            "element_node_ids": [],
            "chunk_count": 0,
            "round1_unit_count": 0,
            "round1_edge_count": 0,
            "round2_edge_count": 0,
            "round2_pair_count": 0,
            "round2_skipped": True,
            "same_source_edge_count": 0,
            "errors": [],
            "skipped": False,
        }

        paper_text = _concat_paper_text(sections)
        if not paper_text:
            empty["skipped"] = True
            return empty

        store = KGStore(config=self.config.get("neo4j"))
        provenance = ProvenanceManager(store)
        embedder = get_embedder(self.config.get("embedding"))
        llm_client = self._resolve_llm_client()

        max_context = int(self.config.get("max_context_tokens", 200_000))
        budget_tokens = llm_call_budget(max_context)
        budget_tokens = max(2_000, budget_tokens - _DEFAULT_PROMPT_OVERHEAD)
        max_chars = budget_tokens * _CHARS_PER_TOKEN

        topk = int(self.config.get("round2_topk", _DEFAULT_TOPK_ROUND2))
        min_conf = float(self.config.get("min_confidence", _DEFAULT_MIN_CONFIDENCE))

        chunks = _split_paper_text(paper_text, max_chars=max_chars)

        errors: List[str] = []
        unit_recs: List[_UnitRec] = []
        round1_edge_count = 0
        round2_edge_count = 0
        round2_pair_count = 0
        round2_skipped = True
        same_source_count = 0

        try:
            # Atomic MERGE so the :Provenance is guaranteed present + has
            # paper_text_hash set before any add_sourced_from runs against
            # it. (get_or_create + SET could race with a concurrent
            # delete_source orphan sweep on the same DB.)
            paper_text_hash = _hash_text(paper_text)
            with store._session() as s:
                s.run(
                    "MERGE (p:Provenance {id: $pid}) "
                    "ON CREATE SET "
                    " p.entity_type = 'paper',"
                    " p.entity_id = $paper_id,"
                    " p.entity_title = $title,"
                    " p.created_at = datetime() "
                    "SET p.paper_text_hash = $h, p.updated_at = datetime()",
                    pid=f"paper_{paper_id}",
                    paper_id=paper_id,
                    title=str(paper_meta.get("title") or paper_id)[:200],
                    h=paper_text_hash,
                )

            element_node_ids = self._write_element_nodes(
                store, provenance, paper_id, tables, formulas, images,
            )

            # ---- (1) extract + relate, chunk by chunk -------------------
            round1_pairs_seen: Set[Tuple[str, str]] = set()
            for chunk_idx, chunk_text in enumerate(chunks):
                u_recs, e_count, pairs_in_chunk = await self._llm_extract_and_relate(
                    store, embedder, provenance, llm_client,
                    paper_id, chunk_text, chunk_idx, min_conf, errors,
                )
                unit_recs.extend(u_recs)
                round1_edge_count += e_count
                round1_pairs_seen |= pairs_in_chunk

            # ---- (2) SAME_SOURCE_PAPER over all units ------------------
            same_source_count = await self._wire_same_source(store, unit_recs)

            # ---- (3) Round 2 cross-chunk stitching ---------------------
            if len(chunks) > 1 and unit_recs and llm_client is not None:
                round2_skipped = False
                round2_edge_count, round2_pair_count = await self._llm_round2(
                    store, llm_client, paper_id, unit_recs,
                    round1_pairs_seen=round1_pairs_seen,
                    budget_tokens=budget_tokens,
                    topk=topk,
                    count_tokens=count_tokens,
                    min_conf=min_conf,
                    errors=errors,
                )
        finally:
            store.close()

        return {
            "paper_id": paper_id,
            "unit_node_ids": [u.node_id for u in unit_recs],
            "element_node_ids": element_node_ids,
            "chunk_count": len(chunks),
            "round1_unit_count": len(unit_recs),
            "round1_edge_count": round1_edge_count,
            "round2_edge_count": round2_edge_count,
            "round2_pair_count": round2_pair_count,
            "round2_skipped": round2_skipped,
            "same_source_edge_count": same_source_count,
            "errors": errors,
            "skipped": False,
        }

    # ---- (0) elements (tables / formulas / images) --------------------

    def _write_element_nodes(
        self,
        store,
        provenance,
        paper_id: str,
        tables: List[Dict[str, Any]],
        formulas: List[Dict[str, Any]],
        images: List[Dict[str, Any]],
    ) -> List[str]:
        ids: List[str] = []

        def _go(rows, kind, src_type, text_cols, summary_col):
            for row in rows:
                rid = row.get("id")
                if rid is None:
                    continue
                preferred_id = _element_node_id(paper_id, kind, rid)
                text = "\n".join(str(row.get(c) or "") for c in text_cols).strip()
                if not text:
                    continue
                content_hash = _hash_text(f"{kind}:{paper_id}:{rid}:{text}")
                if store.get_node(preferred_id):
                    actual_id = preferred_id
                else:
                    other = store.find_by_content_hash(content_hash)
                    if other:
                        actual_id = other.get("id") or other.get("node_id") or preferred_id
                    else:
                        store.create_kgnode(
                            node_id=preferred_id,
                            chunk_text=text[:3000],
                            abstract_summary=str(row.get(summary_col) or "")[:500],
                            content_hash=content_hash,
                            source_type=src_type,
                            source_id=paper_id,
                            metadata={
                                "element_id": rid,
                                "kind": kind,
                                "page_number": _safe_int(row.get("page_number")),
                            },
                        )
                        actual_id = preferred_id
                provenance.add_sourced_from(
                    node_id=actual_id,
                    provenance_type="paper",
                    provenance_id=paper_id,
                    provenance_path=src_type,
                    evidence_text=text[:500],
                    confidence=1.0,
                )
                ids.append(actual_id)

        _go(tables, "table", "paper_table", ["caption", "content"], "caption")
        _go(formulas, "formula", "paper_formula", ["latex", "content"], "latex")
        _go(images, "image", "paper_image", ["caption"], "caption")
        return ids

    # ---- (1) extract + relate ----------------------------------------

    async def _llm_extract_and_relate(
        self,
        store,
        embedder,
        provenance,
        llm_client,
        paper_id: str,
        chunk_text: str,
        chunk_idx: int,
        min_conf: float,
        errors: List[str],
    ) -> Tuple[List[_UnitRec], int, Set[Tuple[str, str]]]:
        if llm_client is None:
            errors.append("llm_client missing — skipping LLM extract")
            return [], 0, set()

        prompt = _EXTRACT_AND_RELATE_PROMPT.format(paper_text=chunk_text)
        try:
            response = await llm_client.chat(prompt)
        except Exception as exc:
            errors.append(f"extract_relate[{paper_id} chunk={chunk_idx}]: {exc}")
            logger.warning("paper_intra_index: extract_relate failed for %s chunk %s: %s",
                           paper_id, chunk_idx, exc)
            return [], 0, set()

        units_raw, relations_raw = _parse_extract_and_relate(response)

        # Write unit nodes; remember the LLM's local id → real node_id map
        # so we can resolve the relations the LLM emitted.
        local_to_node: Dict[str, _UnitRec] = {}
        recs: List[_UnitRec] = []

        for u in units_raw:
            text = str(u.get("text") or "").strip()
            if not text:
                continue
            local_id = str(u.get("id") or "").strip()
            unit_type = str(u.get("type") or "claim").strip().lower() or "claim"
            evidence = str(u.get("evidence") or "")[:500]

            content_hash = _hash_text(text)
            preferred_id = _unit_node_id(paper_id, content_hash)

            existing = store.get_node(preferred_id)
            if not existing:
                other = store.find_by_content_hash(content_hash)
                if other:
                    existing = other

            if existing:
                actual_id = existing.get("id") or existing.get("node_id") or preferred_id
            else:
                try:
                    embedding = await embedder.embed(text)
                except Exception as exc:
                    errors.append(f"embed[{paper_id} chunk={chunk_idx}]: {exc}")
                    embedding = []
                store.create_kgnode(
                    node_id=preferred_id,
                    chunk_text=text,
                    abstract_summary="",
                    content_hash=content_hash,
                    source_type="paper_unit",
                    source_id=paper_id,
                    metadata={
                        "chunk_index": chunk_idx,
                        "unit_type": unit_type,
                    },
                    embedding=embedding or None,
                    abstract_embedding=None,
                )
                actual_id = preferred_id

            provenance.add_sourced_from(
                node_id=actual_id,
                provenance_type="paper",
                provenance_id=paper_id,
                provenance_path="paper_unit",
                evidence_text=evidence,
                confidence=1.0,
            )

            rec = _UnitRec(
                node_id=actual_id,
                text=text,
                abstract_summary="",
                unit_type=unit_type,
                chunk_index=chunk_idx,
                paper_id=paper_id,
            )
            recs.append(rec)
            if local_id:
                local_to_node[local_id] = rec

        edges_kept = 0
        pairs_seen: Set[Tuple[str, str]] = set()
        for rel in relations_raw:
            src_local = str(rel.get("source_id") or "").strip()
            tgt_local = str(rel.get("target_id") or "").strip()
            if not src_local or not tgt_local or src_local == tgt_local:
                continue
            src_rec = local_to_node.get(src_local)
            tgt_rec = local_to_node.get(tgt_local)
            if not src_rec or not tgt_rec:
                continue
            try:
                conf = float(rel.get("confidence", 0.0))
            except (TypeError, ValueError):
                conf = 0.0
            if conf < min_conf:
                continue
            edge = {
                "source_id": src_rec.node_id,
                "target_id": tgt_rec.node_id,
                "relation": str(rel.get("relation", "RELATED_TO")).upper(),
                "confidence": conf,
                "weight": conf,
                "evidence": rel.get("rationale", ""),
                "discovered_by": "intra_paper_round1",
                "phase": "llm",
                "rationale": rel.get("rationale", ""),
            }
            res = await store.add_edge(**edge)
            if not res.get("skipped"):
                edges_kept += 1
            pairs_seen.add(_pair_key(src_rec.node_id, tgt_rec.node_id))

        # Record every pair the chunk *could* have related so round-2
        # only re-evaluates true cross-chunk pairs.
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                pairs_seen.add(_pair_key(recs[i].node_id, recs[j].node_id))

        return recs, edges_kept, pairs_seen

    # ---- (2) SAME_SOURCE_PAPER --------------------------------------

    async def _wire_same_source(self, store, unit_recs: List[_UnitRec]) -> int:
        """Pairwise SAME_SOURCE_PAPER across all intra-paper units.

        ``add_edge`` blocks duplicates regardless of relation, so we
        bypass it here — SAME_SOURCE_PAPER must coexist with any
        other-relation edge already between the same pair (e.g. an LLM
        round-1 EXTENDS). We dedup only on (source, target,
        relation='SAME_SOURCE_PAPER'), and write the missing edges in a
        single bulk Cypher for speed on large papers.
        """
        ids = [u.node_id for u in unit_recs]
        if len(ids) < 2:
            return 0

        with store._session() as session:
            existing: Set[Tuple[str, str]] = set()
            for row in session.run(
                "MATCH (a:KGNode)-[r:RELATED {relation: 'SAME_SOURCE_PAPER'}]->(b:KGNode) "
                "WHERE a.id IN $ids AND b.id IN $ids "
                "RETURN a.id AS s, b.id AS t",
                ids=ids,
            ):
                existing.add((row["s"], row["t"]))

            missing: List[Dict[str, str]] = []
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    if (ids[i], ids[j]) in existing or (ids[j], ids[i]) in existing:
                        continue
                    missing.append({"s": ids[i], "t": ids[j]})

            if not missing:
                return 0

            session.run(
                "UNWIND $rows AS row "
                "MATCH (a:KGNode {id: row.s}) "
                "MATCH (b:KGNode {id: row.t}) "
                "CREATE (a)-[r:RELATED {"
                " relation: 'SAME_SOURCE_PAPER',"
                " relation_text: 'SAME_SOURCE_PAPER',"
                " confidence: 1.0, weight: 1.0, evidence: '',"
                " discovered_by: 'structural', walk_path: null,"
                " visit_frequency: null, rationale: null,"
                " last_hit_at: datetime(), created_at: datetime(),"
                " updated_at: datetime()"
                "}]->(b)",
                rows=missing,
            )
            return len(missing)

    # ---- (3) Round 2 cross-chunk stitching --------------------------

    async def _llm_round2(
        self,
        store,
        llm_client,
        paper_id: str,
        unit_recs: List[_UnitRec],
        *,
        round1_pairs_seen: Set[Tuple[str, str]],
        budget_tokens: int,
        topk: int,
        count_tokens,
        min_conf: float,
        errors: List[str],
    ) -> Tuple[int, int]:
        from src.knowledge_graph.store import KGStore as _KGStore
        from src.knowledge_graph._token_budget import pack_items_to_budget

        id_to_unit = {u.node_id: u for u in unit_recs}
        same_paper_ids = set(id_to_unit.keys())
        candidate_pairs: List[Tuple[_UnitRec, _UnitRec]] = []
        seen_keys: Set[Tuple[str, str]] = set()

        for u in unit_recs:
            embedding = await store.get_node_embedding(u.node_id)
            if not embedding:
                continue
            results = await store.vector_search(
                _KGStore.EMBEDDING_INDEX,
                embedding,
                top_k=max(topk * 4, topk),
            )
            kept = 0
            for r in results:
                cid = r.get("id") or r.get("node_id")
                if not cid or cid == u.node_id or cid not in same_paper_ids:
                    continue
                key = _pair_key(u.node_id, cid)
                if key in seen_keys or key in round1_pairs_seen:
                    continue
                if await store.edge_exists(u.node_id, cid):
                    continue
                if await store.edge_exists(cid, u.node_id):
                    continue
                seen_keys.add(key)
                candidate_pairs.append((id_to_unit[u.node_id], id_to_unit[cid]))
                kept += 1
                if kept >= topk:
                    break

        if not candidate_pairs:
            return 0, 0

        def _pair_tokens(p: Tuple[_UnitRec, _UnitRec]) -> int:
            return (
                count_tokens(p[0].abstract_summary or p[0].text) +
                count_tokens(p[1].abstract_summary or p[1].text) +
                60
            )

        pair_batches = pack_items_to_budget(
            candidate_pairs, _pair_tokens,
            budget_tokens=budget_tokens,
            prompt_overhead=_DEFAULT_PROMPT_OVERHEAD,
            overlap=0,
        )

        edges_kept = 0
        for batch in pair_batches:
            prompt = _ROUND2_PROMPT.format(pairs_text=_format_pairs_for_prompt(batch))
            try:
                response = await llm_client.chat(prompt)
            except Exception as exc:
                errors.append(f"round2_llm[{paper_id}]: {exc}")
                continue
            id_to_rec = {}
            for a, b in batch:
                id_to_rec[a.node_id] = a
                id_to_rec[b.node_id] = b
            for rel in _parse_round2(response):
                src = rel.get("source_id", "")
                tgt = rel.get("target_id", "")
                if src not in id_to_rec or tgt not in id_to_rec or src == tgt:
                    continue
                try:
                    conf = float(rel.get("confidence", 0.0))
                except (TypeError, ValueError):
                    conf = 0.0
                if conf < min_conf:
                    continue
                edge = {
                    "source_id": src, "target_id": tgt,
                    "relation": str(rel.get("relation", "RELATED_TO")).upper(),
                    "confidence": conf, "weight": conf,
                    "evidence": rel.get("rationale", ""),
                    "discovered_by": "intra_paper_round2",
                    "phase": "llm",
                    "rationale": rel.get("rationale", ""),
                }
                res = await store.add_edge(**edge)
                if not res.get("skipped"):
                    edges_kept += 1

        return edges_kept, len(candidate_pairs)

    # ---- helpers ----------------------------------------------------

    def _resolve_llm_client(self):
        client = self.config.get("llm_client")
        if client is not None:
            return client
        api_key = self.config.get("llm_api_key", "")
        if not api_key:
            return None
        from src.llm_provider.factory import LLMFactory
        provider = self.config.get("llm_provider") or self.config.get("llm_model_name", "minimax")
        return LLMFactory.create(
            provider,
            api_key=api_key,
            model=self.config.get("llm_model"),
            base_url=self.config.get("llm_base_url"),
        )

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        return AgentOutput(
            display_type="metrics",
            title="Paper Intra Index",
            content=(
                f"paper_id={result.get('paper_id')} "
                f"chunks={result.get('chunk_count', 0)} "
                f"units={len(result.get('unit_node_ids', []))} "
                f"r1_edges={result.get('round1_edge_count', 0)} "
                f"r2_edges={result.get('round2_edge_count', 0)} "
                f"same_source={result.get('same_source_edge_count', 0)} "
                f"r2_skipped={result.get('round2_skipped', False)}"
            ),
            data={
                "paper_id": result.get("paper_id"),
                "chunk_count": result.get("chunk_count", 0),
            },
        )


def _parse_round2(raw: str) -> List[Dict[str, Any]]:
    """Round-2 prompt only emits a "relations" key — reuse the same JSON
    parser as round-1 by wrapping in a units-less dict."""
    _, rels = _parse_extract_and_relate(raw)
    if rels:
        return rels
    # Some models reply with bare {"relations": [...]}; try to rescue.
    text = raw.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        if nl >= 0:
            text = text[nl + 1:]
        text = text.split("```")[0]
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            r = obj.get("relations") or []
            if isinstance(r, list):
                return r
    except json.JSONDecodeError:
        pass
    return []
