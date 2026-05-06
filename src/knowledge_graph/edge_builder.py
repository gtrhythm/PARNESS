"""Knowledge graph edge builder handling internal, structural, semantic, and retrospect edges."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

from src.knowledge_graph._external_db import open_readonly

logger = logging.getLogger(__name__)


def _parse_json_response(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        if nl >= 0:
            text = text[nl + 1:]
        text = text.split("```")[0]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("[")
    if start >= 0:
        end = text.rfind("]") + 1
        if end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        chunk = text[start:end]
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            chunk = re.sub(r',\s*([}\]])', r'\1', chunk)
            try:
                return json.loads(chunk)
            except json.JSONDecodeError:
                pass
    logger.warning("Failed to parse JSON response")
    return {}


_DEFAULT_DB_PATHS = {
    "papers": "output/papers.db",
    "knowledge_store": "output/knowledge_store/knowledge_store.db",
}

_INTERNAL_RELATIONS_PROMPT = """\
You are a knowledge graph construction assistant. Given the following knowledge units extracted from the same source, identify meaningful relationships between them.

Knowledge Units:
{units_text}

For each pair of units that have a meaningful relationship, provide:
- source_id: the unit id of the source
- target_id: the unit id of the target
- relation: one of [SUPPORTS, CONTRADICTS, EXTENDS, USES_METHOD, BASED_ON, INSPIRED_BY, EXTRACTED_FROM, SAME_SOURCE_PAPER]
- confidence: a float between 0 and 1 indicating how confident you are
- rationale: a brief explanation of why this relationship exists

Return a JSON object with a "relations" key containing a list of relation objects.
Example: {{"relations": [{{"source_id": "id1", "target_id": "id2", "relation": "SUPPORTS", "confidence": 0.85, "rationale": "..."}}]}}
"""

_SEMANTIC_BUCKET_PROMPT = """\
You are a knowledge graph construction assistant. Evaluate the semantic relationships between the following knowledge units.

New Unit:
{new_unit_text}

Candidate Units for Connection:
{candidates_text}

For each candidate that has a meaningful semantic relationship with the new unit, provide:
- target_id: the candidate unit id
- relation: one of [SUPPORTS, CONTRADICTS, EXTENDS, USES_METHOD, BASED_ON, INSPIRED_BY, RELATED_TO]
- confidence: a float between 0 and 1
- rationale: a brief explanation

Return a JSON object with a "relations" key containing a list.
Example: {{"relations": [{{"target_id": "id1", "relation": "EXTENDS", "confidence": 0.75, "rationale": "..."}}]}}
"""

_RETROSPECT_PROMPT = """\
You are a knowledge graph construction assistant. The following pairs of knowledge units are both neighbors of recently added nodes, but no direct edge exists between them. Evaluate whether a direct relationship should be added.

Pairs to Evaluate:
{pairs_text}

For each pair that has a meaningful relationship, provide:
- source_id: the first unit id
- target_id: the second unit id
- relation: one of [SUPPORTS, CONTRADICTS, EXTENDS, USES_METHOD, BASED_ON, INSPIRED_BY, RELATED_TO]
- confidence: a float between 0 and 1
- rationale: a brief explanation

Return a JSON object with a "relations" key containing a list.
Example: {{"relations": [{{"source_id": "id1", "target_id": "id2", "relation": "SUPPORTS", "confidence": 0.8, "rationale": "..."}}]}}
"""


class KGEdgeBuilder:
    def __init__(self, store, config=None) -> None:
        self.store = store
        self.config = config or {}
        self._indexing = self.config.get("indexing", {})
        self._min_confidence = self._indexing.get("min_confidence", 0.6)
        self._top_k = self._indexing.get("top_k_search", 20)
        self._max_candidates_vector = self._indexing.get("max_candidates_vector", 8)
        self._max_candidates_struct = self._indexing.get("max_candidates_struct", 4)
        self._max_retrospect_pairs = self._indexing.get("max_retrospect_pairs", 8)
        self._db_paths = self.config.get("db_paths", _DEFAULT_DB_PATHS)
        self._provenance = None

    def _get_provenance(self):
        if self._provenance is None:
            from src.knowledge_graph.provenance import ProvenanceManager
            self._provenance = ProvenanceManager(self.store)
        return self._provenance

    async def evaluate_internal_relations(
        self,
        llm_client,
        units: List[dict],
        source_type: str,
        source_id: str,
    ) -> List[dict]:
        if len(units) < 2:
            return []

        units_text = self._format_units(units)
        prompt = _INTERNAL_RELATIONS_PROMPT.format(units_text=units_text)

        response = await llm_client.chat(prompt)
        parsed = _parse_json_response(response)

        relations = parsed.get("relations", [])
        valid_ids = {u.get("id") or u.get("node_id") for u in units}
        id_to_node = {}
        for u in units:
            uid = u.get("id") or u.get("node_id")
            nid = u.get("node_id") or uid
            id_to_node[uid] = nid
        logger.info("Phase 4: id_to_node mapping: %s", id_to_node)
        logger.info("Phase 4: valid_ids: %s", valid_ids)

        filtered = []
        for rel in relations:
            conf = float(rel.get("confidence", 0))
            if conf <= self._min_confidence:
                continue
            src = rel.get("source_id", "")
            tgt = rel.get("target_id", "")
            if src in valid_ids and tgt in valid_ids and src != tgt:
                mapped_src = id_to_node.get(src, src)
                mapped_tgt = id_to_node.get(tgt, tgt)
                edge = {
                    "source_id": mapped_src,
                    "target_id": mapped_tgt,
                    "relation": rel.get("relation", "RELATED_TO").upper(),
                    "relation_text": rel.get("relation", ""),
                    "confidence": conf,
                    "weight": conf,
                    "evidence": rel.get("rationale", ""),
                    "discovered_by": "internal",
                    "rationale": rel.get("rationale", ""),
                }
                await self.store.add_edge(**edge)
                filtered.append(edge)

        logger.info(
            "Phase 4 (internal): evaluated %d relations, kept %d edges",
            len(relations),
            len(filtered),
        )
        return filtered

    async def build_structural_edges(
        self,
        new_node_ids: List[str],
        source_type: str,
        source_id: str,
    ) -> List[dict]:
        edges = []

        same_source_nodes = await self.store.find_by_source_id(source_type, source_id)
        same_source_ids = {
            (n.get("id") or n.get("node_id"))
            for n in same_source_nodes
        }

        for nid in new_node_ids:
            for other_id in same_source_ids:
                if other_id == nid or other_id not in new_node_ids:
                    continue
                if await self.store.edge_exists(nid, other_id):
                    continue
                edge = {
                    "source_id": nid,
                    "target_id": other_id,
                    "relation": "SAME_SOURCE_PAPER",
                    "confidence": 1.0,
                    "phase": "structural",
                    "provenance_source_type": source_type,
                    "provenance_source_id": source_id,
                }
                await self.store.add_edge(**edge)
                logger.debug("Phase structural: created edge %s->%s", edge["source_id"], edge["target_id"])
                edges.append(edge)

        new_nodes_data = {}
        for nid in new_node_ids:
            node = self.store.get_node(nid)
            if node:
                new_nodes_data[nid] = node

        fk_edges = await self._build_foreign_key_edges(
            new_node_ids, new_nodes_data, source_type, source_id
        )
        edges.extend(fk_edges)

        logger.info(
            "Phase 5 (structural): built %d edges for source %s/%s",
            len(edges),
            source_type,
            source_id,
        )
        return edges

    async def _build_foreign_key_edges(
        self,
        new_node_ids: List[str],
        new_nodes_data: dict,
        source_type: str,
        source_id: str,
    ) -> List[dict]:
        edges = []
        if source_type == "paper":
            edges.extend(
                await self._query_paper_foreign_keys(new_node_ids, source_id)
            )
        elif source_type == "knowledge":
            edges.extend(
                await self._query_knowledge_store_foreign_keys(
                    new_node_ids, source_id
                )
            )
        return edges

    async def _query_paper_foreign_keys(
        self, new_node_ids: List[str], source_id: str
    ) -> List[dict]:
        # CITES via paper_references is intentionally a no-op right now —
        # papers.db does not currently have a paper_references table, so
        # cross-paper citation edges are deferred to a future ingestion
        # path. NEXT_SECTION across sibling unit-nodes is also a no-op
        # here: it depended on `new_node_ids` being passed in
        # section_order, which the caller can't guarantee. The
        # paper_intra_index adapter builds NEXT_SECTION between proper
        # section-nodes using the real section_order from papers.db.
        edges: List[dict] = []
        db_path = self._db_paths.get("papers", "output/papers.db")

        try:
            with open_readonly(db_path) as conn:
                tables = {
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if "paper_references" not in tables:
                    return edges
                ref_rows = conn.execute(
                    "SELECT reference_paper_id FROM paper_references WHERE paper_id = ?",
                    (source_id,),
                ).fetchall()
                ref_ids = [row["reference_paper_id"] for row in ref_rows]
        except FileNotFoundError:
            return edges
        except sqlite3.Error as e:
            logger.warning("Failed to query papers.db for foreign keys: %s", e)
            return edges

        for ref_id in ref_ids:
            ref_nodes = await self.store.find_by_source_id("paper", ref_id)
            for ref_node in ref_nodes:
                ref_nid = ref_node.get("id") or ref_node.get("node_id")
                for nid in new_node_ids:
                    if await self.store.edge_exists(nid, ref_nid):
                        continue
                    edge = {
                        "source_id": nid,
                        "target_id": ref_nid,
                        "relation": "CITES",
                        "confidence": 0.95,
                        "phase": "structural",
                        "provenance_source_type": "paper",
                        "provenance_source_id": source_id,
                    }
                    await self.store.add_edge(**edge)
                logger.debug("Phase structural: created edge %s->%s", edge["source_id"], edge["target_id"])
                edges.append(edge)

        return edges

    async def _query_knowledge_store_foreign_keys(
        self, new_node_ids: List[str], source_id: str
    ) -> List[dict]:
        edges = []
        db_path = self._db_paths.get(
            "knowledge_store", "output/knowledge_store/knowledge_store.db"
        )

        parent_id: Optional[str] = None
        try:
            with open_readonly(db_path) as conn:
                row = conn.execute(
                    "SELECT parent_id FROM knowledge_entries WHERE id = ?",
                    (source_id,),
                ).fetchone()
                if row and row["parent_id"]:
                    parent_id = row["parent_id"]
        except FileNotFoundError:
            return edges
        except sqlite3.Error as e:
            logger.warning("Failed to query knowledge_store.db: %s", e)
            return edges

        if parent_id:
            parent_nodes = await self.store.find_by_source_id("knowledge", parent_id)
            for parent_node in parent_nodes:
                parent_nid = parent_node.get("id") or parent_node.get("node_id")
                for nid in new_node_ids:
                    if await self.store.edge_exists(nid, parent_nid):
                        continue
                    edge = {
                        "source_id": nid,
                        "target_id": parent_nid,
                        "relation": "EXTRACTED_FROM",
                        "confidence": 0.95,
                        "phase": "structural",
                        "provenance_source_type": "knowledge",
                        "provenance_source_id": source_id,
                    }
                    await self.store.add_edge(**edge)
                logger.debug("Phase structural: created edge %s->%s", edge["source_id"], edge["target_id"])
                edges.append(edge)

        return edges

    async def build_semantic_edges(
        self,
        llm_client,
        new_node_ids: List[str],
        source_type: str,
        source_id: str,
        struct_edge_count: int = 0,
    ) -> dict:
        all_semantic_edges = []
        candidate_stats = {
            "vector_candidates": 0,
            "struct_expanded": 0,
            "total_evaluated": 0,
        }

        struct_neighbor_ids: Set[str] = set()
        for nid in new_node_ids:
            neighbors = self.store.get_neighbors(nid)
            for nb in neighbors:
                nb_id = nb.get("id") or nb.get("node_id")
                if nb_id and nb_id not in new_node_ids:
                    struct_neighbor_ids.add(nb_id)

        from src.knowledge_graph.store import KGStore as _KGStore

        for nid in new_node_ids:
            embedding = await self.store.get_node_embedding(nid)
            if not embedding:
                continue

            vector_results = await self.store.vector_search(
                _KGStore.EMBEDDING_INDEX, embedding, top_k=self._top_k
            )
            abstract_results = []
            try:
                abstract_results = await self.store.vector_search(
                    _KGStore.ABSTRACT_EMBEDDING_INDEX, embedding, top_k=self._top_k
                )
            except Exception:
                pass

            all_candidates: Dict[str, dict] = {}
            for r in vector_results + abstract_results:
                cid = r.get("id") or r.get("node_id")
                if not cid or cid in new_node_ids:
                    continue
                score = r.get("score", 0.0)
                if cid not in all_candidates or score > all_candidates[cid]["score"]:
                    all_candidates[cid] = {
                        "id": cid,
                        "score": score,
                        "source": "vector",
                    }

            candidate_stats["vector_candidates"] += len(all_candidates)

            filtered: Dict[str, dict] = {}
            for cid, cand in all_candidates.items():
                if cid in struct_neighbor_ids:
                    continue
                filtered[cid] = cand

            source_groups: Dict[str, list] = {}
            deduped: Dict[str, dict] = {}
            for cid, cand in filtered.items():
                cnode = self.store.get_node(cid)
                if not cnode:
                    continue
                c_source = cnode.get("source_id", "unknown")
                source_groups.setdefault(c_source, []).append(cand)

            for group in source_groups.values():
                group.sort(key=lambda x: x["score"], reverse=True)
                best = group[0]
                deduped[best["id"]] = best

            expanded: Dict[str, dict] = {}
            for cid in list(deduped.keys()):
                nb_of_cand = self.store.get_neighbors(cid)
                for nb in nb_of_cand:
                    nb_id = nb.get("id") or nb.get("node_id")
                    if (
                        nb_id
                        and nb_id not in new_node_ids
                        and nb_id not in struct_neighbor_ids
                        and nb_id not in deduped
                    ):
                        expanded[nb_id] = {
                            "id": nb_id,
                            "score": 0.0,
                            "source": "struct_expand",
                        }

            candidate_stats["struct_expanded"] += len(expanded)

            merged = list(deduped.values())[: self._max_candidates_vector]
            remaining = (
                self._max_candidates_vector
                + self._max_candidates_struct
                - len(merged)
            )
            if remaining > 0:
                merged.extend(list(expanded.values())[:remaining])
            merged = merged[: self._max_candidates_vector + self._max_candidates_struct]

            if not merged:
                continue

            candidate_stats["total_evaluated"] += len(merged)

            node = self.store.get_node(nid)
            node_text = self._format_unit(node)

            candidates_with_data = []
            for cand in merged:
                cnode = self.store.get_node(cand["id"])
                candidates_with_data.append(
                    {
                        "id": cand["id"],
                        "score": cand["score"],
                        "source": cand["source"],
                        "node": cnode,
                    }
                )

            candidates_text = self._format_candidates(candidates_with_data)
            prompt = _SEMANTIC_BUCKET_PROMPT.format(
                new_unit_text=node_text,
                candidates_text=candidates_text,
            )

            response = await llm_client.chat(prompt)
            parsed = _parse_json_response(response)
            relations = parsed.get("relations", [])

            for rel in relations:
                conf = float(rel.get("confidence", 0))
                if conf <= self._min_confidence:
                    continue
                target_id = rel.get("target_id", "")
                if target_id and target_id not in new_node_ids:
                    edge = {
                        "source_id": nid,
                        "target_id": target_id,
                        "relation": rel.get("relation", "RELATED_TO").upper(),
                        "confidence": conf,
                        "rationale": rel.get("rationale", ""),
                        "phase": "semantic",
                        "provenance_source_type": source_type,
                        "provenance_source_id": source_id,
                    }
                    await self.store.add_edge(**edge)
                    all_semantic_edges.append(edge)

        logger.info(
            "Phase 6 (semantic): created %d edges, candidates=%s",
            len(all_semantic_edges),
            candidate_stats,
        )
        return {
            "semantic_edges": all_semantic_edges,
            "semantic_edge_count": len(all_semantic_edges),
            "candidate_stats": candidate_stats,
        }

    async def retrospect_edges(
        self,
        llm_client,
        new_node_ids: List[str],
        struct_edge_count: int = 0,
        semantic_edge_count: int = 0,
        walk_edge_count: int = 0,
    ) -> List[dict]:
        if not self._indexing.get("enable_retrospect", True):
            return []

        all_neighbors: Dict[str, dict] = {}
        neighbor_of: Dict[str, Set[str]] = {}

        for nid in new_node_ids:
            neighbors = self.store.get_neighbors(nid)
            for nb in neighbors:
                nb_id = nb.get("id") or nb.get("node_id")
                if nb_id and nb_id not in new_node_ids:
                    all_neighbors[nb_id] = nb
                    neighbor_of.setdefault(nb_id, set()).add(nid)

        neighbor_ids = list(all_neighbors.keys())
        pairs: List[Tuple[str, str]] = []

        for i in range(len(neighbor_ids)):
            for j in range(i + 1, len(neighbor_ids)):
                a_id = neighbor_ids[i]
                b_id = neighbor_ids[j]

                a_src = all_neighbors[a_id].get("source_id", a_id)
                b_src = all_neighbors[b_id].get("source_id", b_id)
                if a_src == b_src:
                    continue

                if await self.store.edge_exists(a_id, b_id):
                    continue
                if await self.store.edge_exists(b_id, a_id):
                    continue

                pairs.append((a_id, b_id))
                if len(pairs) >= self._max_retrospect_pairs:
                    break
            if len(pairs) >= self._max_retrospect_pairs:
                break

        if not pairs:
            return []

        pairs_text = self._format_pairs(pairs, all_neighbors)
        prompt = _RETROSPECT_PROMPT.format(pairs_text=pairs_text)

        response = await llm_client.chat(prompt)
        parsed = _parse_json_response(response)
        relations = parsed.get("relations", [])

        edges = []
        for rel in relations:
            conf = float(rel.get("confidence", 0))
            if conf <= self._min_confidence:
                continue
            src = rel.get("source_id", "")
            tgt = rel.get("target_id", "")
            if src and tgt:
                edge = {
                    "source_id": src,
                    "target_id": tgt,
                    "relation": rel.get("relation", "RELATED_TO").upper(),
                    "confidence": conf,
                    "rationale": rel.get("rationale", ""),
                    "phase": "retrospect",
                }
                await self.store.add_edge(**edge)
                edges.append(edge)

        logger.info(
            "Phase 8 (retrospect): evaluated %d pairs, created %d edges",
            len(pairs),
            len(edges),
        )
        return edges

    def _format_units(self, units: List[dict]) -> str:
        parts = []
        for u in units:
            uid = u.get("id") or u.get("node_id", "unknown")
            title = u.get("title", "")
            content = u.get("content", u.get("text", ""))
            unit_type = u.get("type", "")
            parts.append(
                f"[ID: {uid}] Type: {unit_type}\nTitle: {title}\nContent: {content[:500]}"
            )
        return "\n\n---\n\n".join(parts)

    def _format_unit(self, unit: dict) -> str:
        if not unit:
            return "N/A"
        uid = unit.get("id") or unit.get("node_id", "unknown")
        title = unit.get("title", "")
        content = unit.get("content", unit.get("text", ""))
        return f"[ID: {uid}]\nTitle: {title}\nContent: {content[:500]}"

    def _format_candidates(self, candidates: List[dict]) -> str:
        parts = []
        for c in candidates:
            cid = c["id"]
            score = c.get("score", 0.0)
            node = c.get("node") or {}
            title = node.get("title", "N/A")
            content = node.get("content", node.get("text", ""))[:300]
            parts.append(
                f"[ID: {cid}] (similarity: {score:.3f})\nTitle: {title}\nContent: {content}"
            )
        return "\n\n---\n\n".join(parts)

    def _format_pairs(
        self, pairs: List[Tuple[str, str]], node_map: Dict[str, dict]
    ) -> str:
        parts = []
        for a_id, b_id in pairs:
            a = node_map.get(a_id, {})
            b = node_map.get(b_id, {})
            a_title = a.get("title", "N/A")
            b_title = b.get("title", "N/A")
            a_content = a.get("content", a.get("text", ""))[:200]
            b_content = b.get("content", b.get("text", ""))[:200]
            parts.append(
                f"Pair ({a_id}, {b_id}):\n"
                f"  A: {a_title} - {a_content}\n"
                f"  B: {b_title} - {b_content}"
            )
        return "\n\n".join(parts)
