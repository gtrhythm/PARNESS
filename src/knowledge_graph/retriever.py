"""Vector search + graph traversal + query-layer dedup for the knowledge graph."""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class KGRetriever:
    def __init__(self, store, config: Optional[Dict] = None):
        self.store = store
        self._config = config or {}

    async def vector_search(
        self,
        query_embedding: List[float],
        top_k: int = 20,
        search_abstract: bool = True,
        filters: Optional[Dict] = None,
    ) -> List[dict]:
        """Run kNN against the Neo4j vector index(es).

        `filters` (source_type / source_id) are applied post-hoc on the
        returned candidates — adequate for the scale this codebase operates at.
        """
        if not query_embedding:
            return []

        from src.knowledge_graph.store import KGStore as _Store

        indexes = [_Store.EMBEDDING_INDEX]
        if search_abstract:
            indexes.append(_Store.ABSTRACT_EMBEDDING_INDEX)

        all_results: List[dict] = []
        for idx in indexes:
            try:
                hits = await self.store.vector_search(idx, query_embedding, top_k=top_k)
            except Exception as exc:
                logger.warning("Neo4j vector search on %s failed: %s", idx, exc)
                continue
            for hit in hits:
                if filters:
                    if "source_type" in filters and hit.get("source_type") != filters["source_type"]:
                        continue
                    if "source_id" in filters and hit.get("source_id") != filters["source_id"]:
                        continue
                all_results.append(
                    {
                        "node_id": hit.get("node_id", ""),
                        "chunk_text": hit.get("chunk_text", ""),
                        "score": hit.get("score", 0.0),
                        "source_type": hit.get("source_type", ""),
                        "source_id": hit.get("source_id", ""),
                    }
                )

        all_results.sort(key=lambda r: r["score"], reverse=True)
        return all_results[:top_k]

    async def _neo4j_fulltext_search(
        self,
        query_text: str,
        top_k: int,
        filters: Optional[Dict],
    ) -> List[dict]:
        params: Dict[str, Any] = {"query": query_text, "top_k": top_k}
        where_parts: List[str] = []
        if filters:
            if "source_type" in filters:
                params["source_type"] = filters["source_type"]
                where_parts.append("node.source_type = $source_type")
            if "source_id" in filters:
                params["source_id"] = filters["source_id"]
                where_parts.append("node.source_id = $source_id")
        where_clause = ""
        if where_parts:
            where_clause = " AND ".join(where_parts)

        cypher = f"""
        CALL db.index.fulltext.queryNodes('kgnode_text_fulltext', $query)
        YIELD node, score
        {"WHERE " + where_clause if where_clause else ""}
        RETURN node.id AS node_id,
               node.chunk_text AS chunk_text,
               score,
               node.source_type AS source_type,
               node.source_id AS source_id
        ORDER BY score DESC
        LIMIT $top_k
        """
        try:
            records = self.store.run_cypher(cypher, params)
            return [
                {
                    "node_id": rec.get("node_id", ""),
                    "chunk_text": rec.get("chunk_text", ""),
                    "score": rec.get("score", 0.0),
                    "source_type": rec.get("source_type", ""),
                    "source_id": rec.get("source_id", ""),
                }
                for rec in records
            ]
        except Exception as exc:
            logger.warning("Neo4j fulltext search failed: %s", exc)
            return []

    async def traverse_subgraph(
        self,
        node_ids: List[str],
        max_hops: int = 3,
        edge_filter: Optional[Dict] = None,
        include_provenance: bool = True,
    ) -> dict:
        empty = {"nodes": [], "edges": [], "provenances": [], "hop_reached": 0}
        if not node_ids:
            return empty

        try:
            return await self._traverse_impl(node_ids, max_hops, edge_filter, include_provenance)
        except Exception as exc:
            logger.warning("Subgraph traversal failed: %s", exc)
            return empty

    async def _traverse_impl(
        self,
        node_ids: List[str],
        max_hops: int,
        edge_filter: Optional[Dict],
        include_provenance: bool,
    ) -> dict:
        params: Dict[str, Any] = {"node_ids": node_ids}
        constraints: List[str] = []

        if edge_filter:
            min_conf = edge_filter.get("min_confidence")
            if min_conf is not None:
                params["min_confidence"] = min_conf
                constraints.append("ALL(r IN rels WHERE r.confidence >= $min_confidence)")
            discovered_by = edge_filter.get("discovered_by")
            if discovered_by:
                params["discovered_by"] = discovered_by
                constraints.append("ALL(r IN rels WHERE r.discovered_by = $discovered_by)")
            relation_types = edge_filter.get("relation_types")
            if relation_types:
                params["relation_types"] = relation_types
                constraints.append("ALL(r IN rels WHERE r.relation_type IN $relation_types)")

        where_extra = ""
        if constraints:
            where_extra = " AND " + " AND ".join(constraints)

        node_query = f"""
        MATCH (start:KGNode)-[rels:RELATED*1..{max_hops}]-(other:KGNode)
        WHERE start.id IN $node_ids{where_extra}
        WITH DISTINCT other, min(size(rels)) AS hop
        RETURN other.id AS node_id,
               other.chunk_text AS chunk_text,
               other.source_type AS source_type,
               other.source_id AS source_id,
               other.unit_type AS unit_type,
               other.weight AS weight,
               hop
        """
        node_records = self.store.run_cypher(node_query, params)

        seed_query = """
        MATCH (n:KGNode) WHERE n.id IN $node_ids
        RETURN n.id AS node_id,
               n.chunk_text AS chunk_text,
               n.source_type AS source_type,
               n.source_id AS source_id,
               n.unit_type AS unit_type,
               n.weight AS weight
        """
        seed_records = self.store.run_cypher(seed_query, {"node_ids": node_ids})

        nodes: List[dict] = []
        discovered_ids: set = set()
        hop_reached = 0

        for rec in seed_records:
            nid = rec.get("node_id", "")
            if nid:
                discovered_ids.add(nid)
                nodes.append(
                    {
                        "node_id": nid,
                        "chunk_text": rec.get("chunk_text", ""),
                        "source_type": rec.get("source_type", ""),
                        "source_id": rec.get("source_id", ""),
                        "unit_type": rec.get("unit_type", ""),
                        "weight": rec.get("weight", 0.0),
                    }
                )

        for rec in node_records:
            nid = rec.get("node_id", "")
            if nid and nid not in discovered_ids:
                discovered_ids.add(nid)
                nodes.append(
                    {
                        "node_id": nid,
                        "chunk_text": rec.get("chunk_text", ""),
                        "source_type": rec.get("source_type", ""),
                        "source_id": rec.get("source_id", ""),
                        "unit_type": rec.get("unit_type", ""),
                        "weight": rec.get("weight", 0.0),
                    }
                )
            h = rec.get("hop", 0)
            if isinstance(h, int) and h > hop_reached:
                hop_reached = h

        discovered_list = list(discovered_ids)

        if not discovered_list:
            return {"nodes": nodes, "edges": [], "provenances": [], "hop_reached": 0}

        edge_query = """
        MATCH (a:KGNode)-[r:RELATED]-(b:KGNode)
        WHERE a.id IN $ids AND b.id IN $ids
        RETURN a.id AS source,
               b.id AS target,
               type(r) AS rel_type,
               r.confidence AS confidence,
               r.discovered_by AS discovered_by,
               r.relation AS relation_type
        """
        edge_records = self.store.run_cypher(edge_query, {"ids": discovered_list})
        edges: List[dict] = []
        for rec in edge_records:
            edges.append(
                {
                    "source": rec.get("source", ""),
                    "target": rec.get("target", ""),
                    "relation_type": rec.get("relation_type") or rec.get("rel_type", "RELATED"),
                    "confidence": rec.get("confidence", 0.0),
                    "discovered_by": rec.get("discovered_by", ""),
                }
            )

        provenances: List[dict] = []
        if include_provenance:
            prov_query = """
            MATCH (n:KGNode)-[:SOURCED_FROM]->(s:Provenance)
            WHERE n.id IN $ids
            RETURN n.id AS node_id,
                   s.entity_type AS source_type,
                   s.entity_id AS source_id,
                   s.entity_title AS title,
                   '' AS url
            """
            try:
                prov_records = self.store.run_cypher(prov_query, {"ids": discovered_list})
                for rec in prov_records:
                    provenances.append(
                        {
                            "node_id": rec.get("node_id", ""),
                            "source_type": rec.get("source_type", ""),
                            "source_id": rec.get("source_id", ""),
                            "title": rec.get("title", ""),
                            "url": rec.get("url", ""),
                        }
                    )
            except Exception as exc:
                logger.warning("Provenance query failed: %s", exc)

        return {
            "nodes": nodes,
            "edges": edges,
            "provenances": provenances,
            "hop_reached": hop_reached,
        }

    @staticmethod
    def _cosine_sim(text_a: str, text_b: str) -> float:
        if not text_a or not text_b:
            return 0.0
        freq_a: Dict[str, int] = {}
        for w in text_a.lower().split():
            freq_a[w] = freq_a.get(w, 0) + 1
        freq_b: Dict[str, int] = {}
        for w in text_b.lower().split():
            freq_b[w] = freq_b.get(w, 0) + 1
        common = set(freq_a) & set(freq_b)
        if not common:
            return 0.0
        dot = sum(freq_a[w] * freq_b[w] for w in common)
        norm_a = math.sqrt(sum(v * v for v in freq_a.values()))
        norm_b = math.sqrt(sum(v * v for v in freq_b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def deduplicate_results(
        self,
        results: List[dict],
        threshold: float = 0.92,
    ) -> List[dict]:
        if len(results) <= 1:
            return list(results)

        n = len(results)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry

        for i in range(n):
            text_i = results[i].get("chunk_text", "")
            for j in range(i + 1, n):
                text_j = results[j].get("chunk_text", "")
                sim = self._cosine_sim(text_i, text_j)
                if sim > threshold:
                    union(i, j)

        groups: Dict[int, List[int]] = defaultdict(list)
        for i in range(n):
            groups[find(i)].append(i)

        deduped: List[dict] = []
        for indices in groups.values():
            best_idx = max(indices, key=lambda i: results[i].get("score", 0.0))
            representative = dict(results[best_idx])
            merged_sources: List[dict] = []
            seen_pairs: set = set()
            for i in indices:
                src_type = results[i].get("source_type", "")
                src_id = results[i].get("source_id", "")
                pair = (src_type, src_id)
                if pair not in seen_pairs and src_type and src_id:
                    seen_pairs.add(pair)
                    merged_sources.append(
                        {"source_type": src_type, "source_id": src_id}
                    )
            representative["merged_sources"] = merged_sources
            deduped.append(representative)

        deduped.sort(key=lambda r: r.get("score", 0.0), reverse=True)
        return deduped

    async def search(
        self,
        query_text: str,
        top_k: int = 20,
        max_hops: int = 3,
        embedder=None,
    ) -> dict:
        results: List[dict] = []
        query_embedding: Optional[List[float]] = None

        if embedder:
            query_embedding = await embedder.embed(query_text)
            multiplier = self._config.get("query", {}).get("search_multiplier", 2)
            search_abstract = self._config.get("query", {}).get("search_abstract", True)
            results = await self.vector_search(
                query_embedding,
                top_k=top_k * multiplier,
                search_abstract=search_abstract,
            )

        if not results:
            results = await self._neo4j_fulltext_search(query_text, top_k, None)

        node_ids = list({r["node_id"] for r in results if r.get("node_id")})

        subgraph = await self.traverse_subgraph(node_ids, max_hops=max_hops)

        threshold = self._config.get("query", {}).get("dedup_threshold", 0.92)
        deduped = self.deduplicate_results(results, threshold=threshold)

        return {
            "results": deduped[:top_k],
            "subgraph": subgraph,
            "query_embedding": query_embedding,
            "total_before_dedup": len(results),
            "total_after_dedup": len(deduped),
        }
