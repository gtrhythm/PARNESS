"""Graph statistics and health checks for the knowledge graph."""

from __future__ import annotations

import logging
import random
from collections import Counter
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class KGMetrics:
    def __init__(self, store: Any) -> None:
        self._store = store

    async def get_graph_stats(self) -> Dict[str, Any]:
        node_count_rows = await self._store.run_cypher(
            "MATCH (n) RETURN count(n) AS cnt"
        )
        edge_count_rows = await self._store.run_cypher(
            "MATCH ()-[r]->() RETURN count(r) AS cnt"
        )
        provenance_rows = await self._store.run_cypher(
            "MATCH ()-[r]->() RETURN DISTINCT r.discovered_by AS src, count(r) AS cnt"
        )

        source_type_rows = await self._store.run_cypher(
            "MATCH (n) RETURN n.source_type AS source_type, count(n) AS cnt"
        )
        discovered_by_rows = await self._store.run_cypher(
            "MATCH ()-[r]->() RETURN r.discovered_by AS discovered_by, count(r) AS cnt"
        )
        relation_rows = await self._store.run_cypher(
            "MATCH ()-[r]->() RETURN type(r) AS relation, count(r) AS cnt"
        )

        nodes_by_source_type = {row["source_type"] or "unknown": row["cnt"] for row in source_type_rows}
        edges_by_discovered_by = {row["discovered_by"] or "unknown": row["cnt"] for row in discovered_by_rows}
        edges_by_relation = {row["relation"]: row["cnt"] for row in relation_rows}

        total_nodes = node_count_rows[0]["cnt"] if node_count_rows else 0
        total_edges = edge_count_rows[0]["cnt"] if edge_count_rows else 0
        total_provenances = len(provenance_rows)

        return {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "total_provenances": total_provenances,
            "nodes_by_source_type": nodes_by_source_type,
            "edges_by_discovered_by": edges_by_discovered_by,
            "edges_by_relation": edges_by_relation,
        }

    async def get_node_degree_distribution(self) -> Dict[str, Any]:
        rows = await self._store.run_cypher(
            """
            MATCH (n)
            OPTIONAL MATCH (n)-[r]-()
            WITH n, count(r) AS degree
            RETURN degree, count(n) AS node_count
            ORDER BY degree
            """
        )
        histogram = {str(row["degree"]): row["node_count"] for row in rows}

        stats_rows = await self._store.run_cypher(
            """
            MATCH (n)
            OPTIONAL MATCH (n)-[r]-()
            WITH n, count(r) AS degree
            RETURN avg(degree) AS avg_degree,
                   max(degree) AS max_degree,
                   min(degree) AS min_degree,
                   stdev(degree) AS stdev_degree
            """
        )
        stats = stats_rows[0] if stats_rows else {}

        return {
            "histogram": histogram,
            "avg_degree": stats.get("avg_degree", 0),
            "max_degree": stats.get("max_degree", 0),
            "min_degree": stats.get("min_degree", 0),
            "stdev_degree": stats.get("stdev_degree", 0),
        }

    async def get_connectivity_stats(self) -> Dict[str, Any]:
        component_rows = await self._store.run_cypher(
            """
            MATCH (n)
            OPTIONAL MATCH (n)-[r*..50]-(m)
            WITH n, collect(DISTINCT id(m)) AS component_members
            RETURN count(DISTINCT component_members) AS component_count
            """
        )

        wcc_rows = await self._store.run_cypher(
            """
            MATCH (n)
            WHERE NOT (n)-[:RELATED]-(())
            RETURN count(n) AS isolated_count
            """
        )
        isolated = wcc_rows[0]["isolated_count"] if wcc_rows else 0

        component_count_rows = await self._store.run_cypher(
            """
            MATCH (n)
            WITH n ORDER BY id(n)
            WITH collect(n) AS nodes
            CALL {
                WITH nodes
                UNWIND range(0, size(nodes)-1) AS i
                WITH nodes, i
                MATCH (nodes[i])-[r:RELATED]-(m)
                WITH nodes, i, collect(DISTINCT id(m)) AS neighbors
                RETURN i, neighbors
            }
            RETURN count(DISTINCT i) AS total_nodes_with_edges
            """
        )

        avg_path_length = await self._sample_average_path_length()

        return {
            "connected_components": component_rows[0]["component_count"] if component_rows else 0,
            "isolated_nodes": isolated,
            "average_path_length_sample": avg_path_length,
        }

    async def _sample_average_path_length(self, sample_size: int = 100) -> float:
        node_rows = await self._store.run_cypher("MATCH (n) RETURN id(n) AS nid")
        if len(node_rows) < 2:
            return 0.0

        sample_n = min(sample_size, len(node_rows))
        sampled = random.sample(node_rows, sample_n)
        total_length = 0.0
        pairs = 0

        for row in sampled:
            nid = row["nid"]
            sp_rows = await self._store.run_cypher(
                """
                MATCH (n) WHERE id(n) = $nid
                MATCH (n)-[r:RELATED*..6]-(m)
                WHERE n <> m
                WITH m, min(length(r)) AS dist
                RETURN avg(dist) AS avg_dist
                """,
                nid=nid,
            )
            if sp_rows and sp_rows[0]["avg_dist"] is not None:
                total_length += sp_rows[0]["avg_dist"]
                pairs += 1

        return round(total_length / pairs, 4) if pairs > 0 else 0.0

    async def get_health_check(self) -> Dict[str, Any]:
        stats = await self.get_graph_stats()
        degree_dist = await self.get_node_degree_distribution()
        connectivity = await self.get_connectivity_stats()

        issues: List[str] = []

        if stats["total_nodes"] == 0:
            issues.append("Graph has no nodes")
        if stats["total_edges"] == 0:
            issues.append("Graph has no edges")

        total_nodes = stats["total_nodes"]
        if total_nodes > 0:
            isolated_ratio = connectivity["isolated_nodes"] / total_nodes
            if isolated_ratio > 0.5:
                issues.append(
                    f"High isolation ratio: {isolated_ratio:.1%} of nodes are isolated"
                )

        max_deg = degree_dist.get("max_degree", 0)
        avg_deg = degree_dist.get("avg_degree", 0)
        if max_deg > 0 and avg_deg > 0 and max_deg / avg_deg > 100:
            issues.append(
                f"Extreme degree skew: max={max_deg}, avg={avg_deg:.1f}"
            )

        orphan_rows = await self._store.run_cypher(
            """
            MATCH (n)
            WHERE NOT (n)--()
            RETURN count(n) AS cnt
            """
        )
        orphan_count = orphan_rows[0]["cnt"] if orphan_rows else 0
        if orphan_count > 0 and total_nodes > 0:
            orphan_ratio = orphan_count / total_nodes
            if orphan_ratio > 0.3:
                issues.append(
                    f"Many orphan nodes: {orphan_count} ({orphan_ratio:.1%})"
                )

        return {
            "healthy": len(issues) == 0,
            "issues": issues,
            "summary": {
                "total_nodes": stats["total_nodes"],
                "total_edges": stats["total_edges"],
                "isolated_nodes": connectivity["isolated_nodes"],
                "orphan_nodes": orphan_count,
                "max_degree": max_deg,
                "avg_degree": avg_deg,
            },
        }

    async def get_source_coverage(self) -> Dict[str, Any]:
        indexed_rows = await self._store.run_cypher(
            "MATCH (n) RETURN n.source_type AS source_type, count(n) AS cnt"
        )
        indexed = {row["source_type"] or "unknown": row["cnt"] for row in indexed_rows}
        total_indexed = sum(indexed.values())

        try:
            from src.db.dao.knowledge_store_dao import KnowledgeStoreDAO

            dao = KnowledgeStoreDAO()
            sqlite_counts: Dict[str, int] = {}
            tables = ["insights", "raw_ideas", "seeds", "seed_clusters", "experiments"]
            for table in tables:
                try:
                    row = dao.db.execute(f"SELECT count(*) AS cnt FROM {table}").fetchone()
                    sqlite_counts[table] = row["cnt"] if row else 0
                except Exception:
                    sqlite_counts[table] = 0
            dao.close()
        except Exception:
            sqlite_counts = {}

        total_sqlite = sum(sqlite_counts.values())
        coverage = round(total_indexed / total_sqlite, 4) if total_sqlite > 0 else 0.0

        return {
            "total_indexed_in_graph": total_indexed,
            "total_in_sqlite": total_sqlite,
            "coverage_ratio": coverage,
            "indexed_by_source_type": indexed,
            "sqlite_table_counts": sqlite_counts,
        }
