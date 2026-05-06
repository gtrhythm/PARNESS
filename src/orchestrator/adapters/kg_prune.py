"""KG edge pruning adapter."""

import logging
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class KGPruneModule(BaseModule):
    module_name = "kg_prune"

    INPUT_SPEC = {
        "max_edges_per_node": {"type": "int", "required": False, "default": 20},
        "min_weight": {"type": "float", "required": False, "default": 0.3},
        "dry_run": {"type": "bool", "required": False, "default": True},
    }
    OUTPUT_SPEC = {
        "pruned_count": {"type": "int"},
        "pruned_by_degree": {"type": "int"},
        "pruned_by_weight": {"type": "int"},
        "pruned_by_decay": {"type": "int"},
        "total_edges_before": {"type": "int"},
        "total_edges_after": {"type": "int"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.pruner import KGPruner
        from src.knowledge_graph.store import KGStore

        max_edges_per_node = inputs.get("max_edges_per_node", 20)
        min_weight = inputs.get("min_weight", 0.3)
        dry_run = inputs.get("dry_run", True)

        store = KGStore(config=self.config.get("neo4j"))
        try:
            pruner = KGPruner(store, self.config.get("pruning"))
            result = await pruner.prune_edges(max_edges_per_node, min_weight, dry_run)
        finally:
            store.close()

        logger.info(
            "KGPrune: pruned %d edges (%d by degree, %d by weight, %d by decay) "
            "total %d -> %d%s",
            result.get("pruned_count", 0),
            result.get("pruned_by_degree", 0),
            result.get("pruned_by_weight", 0),
            result.get("pruned_by_decay", 0),
            result.get("total_edges_before", 0),
            result.get("total_edges_after", 0),
            " (dry_run)" if dry_run else "",
        )

        return {
            "pruned_count": result.get("pruned_count", 0),
            "pruned_by_degree": result.get("pruned_by_degree", 0),
            "pruned_by_weight": result.get("pruned_by_weight", 0),
            "pruned_by_decay": result.get("pruned_by_decay", 0),
            "total_edges_before": result.get("total_edges_before", 0),
            "total_edges_after": result.get("total_edges_after", 0),
        }
