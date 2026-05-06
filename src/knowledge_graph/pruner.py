"""Three-layer edge pruning strategy for the knowledge graph."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.knowledge_graph.config import PruningConfig

logger = logging.getLogger(__name__)

_PROTECTED_RELATIONS = frozenset({
    "SAME_SOURCE_PAPER",
    "CITES",
    "NEXT_SECTION",
    "EXTRACTED_FROM",
    "INSPIRED_BY",
    "EXTENDS",
    "TESTS_IDEA",
    "IMPLEMENTS",
    "CROSS_DOMAIN",
    "SUPPORTS",
    "REFUTES",
    "SAME_SEED_CLUSTER",
    "BASED_ON_INSIGHT",
    "EXPLORATION_OF",
    "ROUND_OF",
    "METRIC_OF",
    "SAME_SOURCE_IDEA",
    "SAME_SOURCE_EXPERIMENT",
})


class KGPruner:
    def __init__(self, store: Any, config: Optional[PruningConfig] = None) -> None:
        self._store = store
        self._config = config or PruningConfig()
        self._protected = _PROTECTED_RELATIONS | frozenset(self._config.protected_relations)

    async def prune_edges(
        self,
        max_edges_per_node: int = 20,
        min_weight: float = 0.3,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        total_before = await self._count_edges()
        pruned_by_degree = await self._prune_by_degree(max_edges_per_node, dry_run)
        pruned_by_weight = await self._prune_by_weight(min_weight, dry_run)
        pruned_by_decay = await self._prune_by_decay(dry_run)
        total_after = await self._count_edges() if not dry_run else total_before

        pruned_count = pruned_by_degree + pruned_by_weight + pruned_by_decay
        return {
            "pruned_count": pruned_count,
            "pruned_by_degree": pruned_by_degree,
            "pruned_by_weight": pruned_by_weight,
            "pruned_by_decay": pruned_by_decay,
            "total_edges_before": total_before,
            "total_edges_after": total_after,
        }

    async def _count_edges(self) -> int:
        result = self._store.run_cypher(
            "MATCH ()-[r]->() RETURN count(r) AS cnt"
        )
        return result[0]["cnt"] if result else 0

    async def _prune_by_degree(self, max_edges_per_node: int, dry_run: bool) -> int:
        relation_clause = self._build_protected_relation_clause("r.relation")
        rows = self._store.run_cypher(
            f"""
            MATCH (n)-[r:RELATED]->(m)
            WHERE {relation_clause}
              AND r.discovered_by <> 'structured'
            WITH n, r, m
            ORDER BY n.uid, r.weight DESC
            WITH n, collect(r) AS edges
            WHERE size(edges) > $max_edges
            UNWIND edges[$max_edges..] AS drop_edge
            RETURN id(drop_edge) AS edge_id
            """,
            max_edges=max_edges_per_node,
        )
        edge_ids = [row["edge_id"] for row in rows]
        if not dry_run and edge_ids:
            await self._delete_edges_by_ids(edge_ids)
        return len(edge_ids)

    async def _prune_by_weight(self, min_weight: float, dry_run: bool) -> int:
        relation_clause = self._build_protected_relation_clause("r.relation")
        rows = self._store.run_cypher(
            f"""
            MATCH ()-[r]->()
            WHERE r.weight < $min_weight
              AND r.discovered_by <> 'structured'
              AND {relation_clause}
            RETURN id(r) AS edge_id
            """,
            min_weight=min_weight,
        )
        edge_ids = [row["edge_id"] for row in rows]
        if not dry_run and edge_ids:
            await self._delete_edges_by_ids(edge_ids)
        return len(edge_ids)

    async def _prune_by_decay(self, dry_run: bool) -> int:
        decay_factor = self._config.decay_factor
        decay_min_weight = self._config.decay_min_weight
        now = datetime.now(timezone.utc)

        relation_clause = self._build_protected_relation_clause("r.relation")
        rows = self._store.run_cypher(
            f"""
            MATCH ()-[r]->()
            WHERE r.last_hit_at IS NOT NULL
              AND duration.between(datetime(r.last_hit_at), datetime()).days >= 30
              AND r.discovered_by <> 'structured'
              AND {relation_clause}
            RETURN id(r) AS edge_id,
                   r.weight AS weight,
                   r.last_hit_at AS last_hit_at
            """
        )

        to_delete: List[int] = []
        to_update: List[Dict[str, Any]] = []

        for row in rows:
            last_hit = datetime.fromisoformat(row["last_hit_at"].replace("Z", "+00:00"))
            days = (now - last_hit).days
            periods = days / 30
            new_weight = row["weight"] * (decay_factor ** periods)
            if new_weight < decay_min_weight:
                to_delete.append(row["edge_id"])
            else:
                to_update.append({"edge_id": row["edge_id"], "weight": round(new_weight, 6)})

        if not dry_run:
            if to_delete:
                await self._delete_edges_by_ids(to_delete)
            for entry in to_update:
                self._store.run_cypher(
                    "MATCH ()-[r]->() WHERE id(r) = $edge_id SET r.weight = $weight",
                    edge_id=entry["edge_id"],
                    weight=entry["weight"],
                )

        return len(to_delete)

    async def _delete_edges_by_ids(self, edge_ids: List[int]) -> None:
        batch_size = 500
        for i in range(0, len(edge_ids), batch_size):
            batch = edge_ids[i : i + batch_size]
            self._store.run_cypher(
                "MATCH ()-[r]->() WHERE id(r) IN $ids DELETE r",
                ids=batch,
            )

    def _build_protected_relation_clause(self, field: str) -> str:
        if not self._protected:
            return "true"
        relations = ", ".join(f"'{r}'" for r in sorted(self._protected))
        return f"NOT {field} IN [{relations}]"
