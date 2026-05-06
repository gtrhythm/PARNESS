"""kg_cross_paper_discover — find semantic relations between knowledge
units that come from *different* papers.

Operates entirely on the KG (no papers.db access). Algorithm:

  1. for every unit in the input paper, take its embedding and run a
     Neo4j vector kNN; keep candidates whose source_id is a *different*
     paper, drop any already connected by a :RELATED edge in either
     direction
  2. dedupe (a, b) ≡ (b, a) into a candidate-pair set
  3. pack the pairs into LLM-budget batches (one third of the model
     context window) and ask the LLM, per batch, which pairs have a
     meaningful relation and what kind
  4. write surviving relations as :RELATED edges with
     ``discovered_by='cross_paper_semantic'``
  5. stamp the paper's :Provenance with ``cross_paper_indexed_at`` so
     the driver can short-circuit on subsequent runs

Why no chunker / source DB:
  * units already exist with embeddings + chunk_text
  * cross-paper discovery is fundamentally a *graph* operation
"""

from __future__ import annotations

import json
import logging
import re
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
    paper_id: str
    text: str


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


_CROSS_PAPER_PROMPT = """\
You are linking knowledge units across distinct research papers. For \
each PAIR below, decide whether unit A and unit B (from different \
papers) have a meaningful semantic relation.

Pairs:
{pairs_text}

For pairs WITH a clear relation reply with:
  - pair_id   : the bracketed id given above (e.g. "p001")
  - relation  : ONE of [SUPPORTS, CONTRADICTS, EXTENDS, USES_METHOD,
                BASED_ON, INSPIRED_BY, ADDRESSES, GENERALIZES,
                SPECIAL_CASE_OF]
  - confidence: float 0..1
  - rationale : brief justification (under 200 chars)

Skip pairs with no clear relation. Do NOT invent pair_ids.
Pay special attention to INSPIRED_BY / EXTENDS / BASED_ON for the
"earlier paper inspired later paper" case.

Return strictly valid JSON: {{"relations": [...]}}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pair_key(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def _format_pairs_for_prompt(
    pairs: List[Tuple[_UnitRec, _UnitRec]],
    pair_ids: List[str],
) -> str:
    parts = []
    for pid, (a, b) in zip(pair_ids, pairs):
        a_text = a.text[:600]
        b_text = b.text[:600]
        parts.append(
            f"[{pid}]\n"
            f"  PAPER {a.paper_id}, A: {a_text}\n"
            f"  PAPER {b.paper_id}, B: {b_text}"
        )
    return "\n\n".join(parts)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        if nl >= 0:
            text = text[nl + 1:]
        text = text.split("```")[0]
    return text.strip()


_TRAILING_COMMA_RE = re.compile(r",(\s*[\]}])")
_SMART_QUOTE_PAIRS = (
    ("“", '"'), ("”", '"'),
    ("‘", "'"), ("’", "'"),
    ("«", '"'), ("»", '"'),
)
_PYTHON_LITERAL_RE = re.compile(r"\b(True|False|None)\b")
_PYTHON_LITERAL_MAP = {"True": "true", "False": "false", "None": "null"}


def _isolate_json_object(text: str) -> str:
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
    last = text.rfind("}")
    if last > start:
        return text[start:last + 1]
    return ""


def _relax_json(text: str) -> str:
    for bad, good in _SMART_QUOTE_PAIRS:
        text = text.replace(bad, good)
    text = _TRAILING_COMMA_RE.sub(r"\1", text)
    text = _PYTHON_LITERAL_RE.sub(
        lambda m: _PYTHON_LITERAL_MAP[m.group(1)],
        text,
    )
    return text


def _try_parse_relations(raw: str) -> List[Dict[str, Any]]:
    """Same lenient strategy as paper_intra_index — try strict, isolate
    the balanced {..}, then apply soft cleanups."""
    if not raw:
        return []
    candidates: List[str] = [raw.strip()]
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
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            break
    if not isinstance(obj, dict):
        logger.warning(
            "kg_cross_paper_discover: failed to parse LLM JSON (head=%r)",
            raw[:200],
        )
        return []
    rels = obj.get("relations") or []
    return rels if isinstance(rels, list) else []


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------


_DEFAULT_TOPK = 8
_DEFAULT_MIN_CONFIDENCE = 0.6
_DEFAULT_PROMPT_OVERHEAD = 2_000
_VALID_RELATIONS = {
    "SUPPORTS", "CONTRADICTS", "EXTENDS", "USES_METHOD", "BASED_ON",
    "INSPIRED_BY", "ADDRESSES", "GENERALIZES", "SPECIAL_CASE_OF",
}


class KGCrossPaperDiscoverModule(BaseModule):
    """Cross-paper semantic edge discovery for one source paper."""

    module_name = "kg_cross_paper_discover"

    INPUT_SPEC = {
        "paper_id": {"type": "str", "required": True},
        "top_k_per_unit": {"type": "int", "required": False, "default": _DEFAULT_TOPK},
        "min_confidence": {"type": "float", "required": False, "default": _DEFAULT_MIN_CONFIDENCE},
        "max_context_tokens": {"type": "int", "required": False, "default": 200_000},
        "max_evaluations": {"type": "int", "required": False, "default": 10_000},
    }
    OUTPUT_SPEC = {
        "paper_id": {"type": "str"},
        "unit_count": {"type": "int"},
        "candidate_pair_count": {"type": "int"},
        "evaluated_pair_count": {"type": "int"},
        "cross_paper_edge_count": {"type": "int"},
        "llm_calls": {"type": "int"},
        "errors": {"type": "list"},
        "skipped": {"type": "bool"},
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.store import KGStore
        from src.knowledge_graph._token_budget import (
            count_tokens, llm_call_budget, pack_items_to_budget,
        )

        paper_id = str(inputs["paper_id"])
        top_k = int(inputs.get("top_k_per_unit") or _DEFAULT_TOPK)
        min_conf = float(inputs.get("min_confidence") or _DEFAULT_MIN_CONFIDENCE)
        max_context = int(inputs.get("max_context_tokens") or 200_000)
        max_evals = int(inputs.get("max_evaluations") or 10_000)

        budget_tokens = max(2_000, llm_call_budget(max_context) - _DEFAULT_PROMPT_OVERHEAD)

        result: Dict[str, Any] = {
            "paper_id": paper_id,
            "unit_count": 0,
            "candidate_pair_count": 0,
            "evaluated_pair_count": 0,
            "cross_paper_edge_count": 0,
            "llm_calls": 0,
            "errors": [],
            "skipped": False,
        }

        store = KGStore(config=self.config.get("neo4j"))
        llm_client = self._resolve_llm_client()

        if llm_client is None:
            result["errors"].append("llm_client missing")
            result["skipped"] = True
            store.close()
            return result

        try:
            units = self._load_units(store, paper_id)
            result["unit_count"] = len(units)
            if not units:
                result["skipped"] = True
                return result

            # ---- (1) candidate generation -------------------------------
            candidate_pairs, errors = await self._collect_candidates(
                store, units, paper_id, top_k,
            )
            result["errors"].extend(errors)
            result["candidate_pair_count"] = len(candidate_pairs)
            if not candidate_pairs:
                self._stamp_provenance(store, paper_id, evaluated=0, edges=0)
                return result

            if len(candidate_pairs) > max_evals:
                logger.info(
                    "kg_cross_paper_discover[%s]: capping %d candidate pairs to %d",
                    paper_id, len(candidate_pairs), max_evals,
                )
                candidate_pairs = candidate_pairs[:max_evals]

            # ---- (2) pack into LLM-budget batches -----------------------
            def _pair_tokens(p: Tuple[_UnitRec, _UnitRec]) -> int:
                return count_tokens(p[0].text) + count_tokens(p[1].text) + 80

            batches = pack_items_to_budget(
                candidate_pairs, _pair_tokens,
                budget_tokens=budget_tokens,
                prompt_overhead=_DEFAULT_PROMPT_OVERHEAD,
                overlap=0,
            )

            # ---- (3) per-batch LLM evaluation ---------------------------
            edges_kept = 0
            evaluated = 0
            llm_calls = 0
            for batch in batches:
                evaluated += len(batch)
                pair_ids = [f"p{i:03d}" for i in range(len(batch))]
                prompt = _CROSS_PAPER_PROMPT.format(
                    pairs_text=_format_pairs_for_prompt(batch, pair_ids),
                )
                try:
                    response = await llm_client.chat(prompt)
                except Exception as exc:
                    result["errors"].append(f"llm_call: {exc}")
                    continue
                llm_calls += 1
                rels = _try_parse_relations(response)
                pid_to_pair = dict(zip(pair_ids, batch))

                for rel in rels:
                    pid = str(rel.get("pair_id") or "").strip()
                    pair = pid_to_pair.get(pid)
                    if not pair:
                        continue
                    relation = str(rel.get("relation") or "").strip().upper()
                    if relation not in _VALID_RELATIONS:
                        # Allow the LLM to use unknown relations but
                        # don't write them — emit warning so the user can
                        # see them in the per-paper errors list.
                        result["errors"].append(
                            f"unrecognized_relation:{relation}"
                        )
                        continue
                    try:
                        conf = float(rel.get("confidence", 0))
                    except (TypeError, ValueError):
                        conf = 0.0
                    if conf < min_conf:
                        continue
                    a, b = pair
                    edge = {
                        "source_id": a.node_id,
                        "target_id": b.node_id,
                        "relation": relation,
                        "confidence": conf,
                        "weight": conf,
                        "evidence": str(rel.get("rationale") or "")[:500],
                        "discovered_by": "cross_paper_semantic",
                        "phase": "llm",
                        "rationale": str(rel.get("rationale") or "")[:500],
                    }
                    res = await store.add_edge(**edge)
                    if not res.get("skipped"):
                        edges_kept += 1

            result["evaluated_pair_count"] = evaluated
            result["cross_paper_edge_count"] = edges_kept
            result["llm_calls"] = llm_calls

            self._stamp_provenance(
                store, paper_id, evaluated=evaluated, edges=edges_kept,
            )
        finally:
            store.close()

        return result

    # ---- internals ---------------------------------------------------

    def _load_units(self, store, paper_id: str) -> List[_UnitRec]:
        with store._session() as s:
            rows = s.run(
                "MATCH (n:KGNode {source_type: 'paper_unit', source_id: $pid}) "
                "RETURN n.id AS id, n.chunk_text AS text",
                pid=paper_id,
            ).data()
        out = []
        for r in rows:
            text = (r.get("text") or "").strip()
            if not text:
                continue
            out.append(_UnitRec(
                node_id=r["id"],
                paper_id=paper_id,
                text=text,
            ))
        return out

    async def _collect_candidates(
        self,
        store,
        units: List[_UnitRec],
        paper_id: str,
        top_k: int,
    ) -> Tuple[List[Tuple[_UnitRec, _UnitRec]], List[str]]:
        from src.knowledge_graph.store import KGStore as _KGStore

        # Cache target unit recs we look up so repeated kNN hits don't
        # re-fetch the same node.
        rec_cache: Dict[str, _UnitRec] = {u.node_id: u for u in units}
        seen_keys: Set[Tuple[str, str]] = set()
        pairs: List[Tuple[_UnitRec, _UnitRec]] = []
        errors: List[str] = []

        for u in units:
            embedding = await store.get_node_embedding(u.node_id)
            if not embedding:
                continue
            try:
                results = await store.vector_search(
                    _KGStore.EMBEDDING_INDEX,
                    embedding,
                    top_k=max(top_k * 4, top_k),
                )
            except Exception as exc:
                errors.append(f"vector_search[{u.node_id}]: {exc}")
                continue

            kept = 0
            for r in results:
                cid = r.get("id") or r.get("node_id")
                if not cid or cid == u.node_id:
                    continue
                if r.get("source_type") != "paper_unit":
                    continue
                cand_pid = r.get("source_id")
                if not cand_pid or cand_pid == paper_id:
                    continue
                key = _pair_key(u.node_id, cid)
                if key in seen_keys:
                    continue
                # Existing :RELATED in either direction → skip.
                if await store.edge_exists(u.node_id, cid):
                    continue
                if await store.edge_exists(cid, u.node_id):
                    continue
                seen_keys.add(key)
                if cid not in rec_cache:
                    rec_cache[cid] = _UnitRec(
                        node_id=cid,
                        paper_id=str(cand_pid),
                        text=str(r.get("chunk_text") or "").strip(),
                    )
                pairs.append((u, rec_cache[cid]))
                kept += 1
                if kept >= top_k:
                    break

        return pairs, errors

    def _stamp_provenance(self, store, paper_id: str, evaluated: int, edges: int) -> None:
        prov_id = f"paper_{paper_id}"
        with store._session() as s:
            s.run(
                "MATCH (p:Provenance {id: $pid}) "
                "SET p.cross_paper_indexed_at = datetime(),"
                "    p.cross_paper_eval_count = $evaluated,"
                "    p.cross_paper_edge_count = $edges",
                pid=prov_id,
                evaluated=int(evaluated),
                edges=int(edges),
            )

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
            title="KG Cross-Paper Discover",
            content=(
                f"paper_id={result.get('paper_id')} "
                f"units={result.get('unit_count')} "
                f"candidates={result.get('candidate_pair_count')} "
                f"evaluated={result.get('evaluated_pair_count')} "
                f"edges={result.get('cross_paper_edge_count')} "
                f"llm_calls={result.get('llm_calls')}"
            ),
            data={
                "paper_id": result.get("paper_id"),
                "cross_paper_edge_count": result.get("cross_paper_edge_count", 0),
            },
        )
