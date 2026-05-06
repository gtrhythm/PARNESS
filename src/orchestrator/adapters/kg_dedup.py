"""KG dedup adapter: content-hash based duplicate detection."""

import hashlib
import logging
from typing import Any, Dict, Optional

from .base import BaseModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class KGDedupModule(BaseModule):
    module_name = "kg_dedup"

    INPUT_SPEC = {
        "units": {"type": "list", "required": True},
        "source_type": {"type": "str", "required": True},
        "source_id": {"type": "str", "required": True},
    }
    OUTPUT_SPEC = {
        "new_units": {"type": "list"},
        "duplicate_units": {"type": "list"},
        "new_count": {"type": "int"},
        "dup_count": {"type": "int"},
        "source_type": {"type": "str"},
        "source_id": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.store import KGStore

        units = inputs["units"]
        source_type = inputs["source_type"]
        source_id = inputs["source_id"]

        neo4j_config = self.config.get("neo4j")
        store = KGStore(config=neo4j_config)

        new_units = []
        duplicate_units = []

        try:
            for unit in units:
                text = unit.get("text", unit.get("chunk_text", ""))
                content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                unit["content_hash"] = content_hash

                existing = store.find_by_content_hash(content_hash)
                if existing is not None:
                    unit["existing_node_id"] = existing.get("id", "")
                    duplicate_units.append(unit)
                else:
                    new_units.append(unit)
        finally:
            store.close()

        logger.info(
            "KGDedup: %d new, %d duplicates from %s/%s",
            len(new_units), len(duplicate_units), source_type, source_id,
        )

        return {
            "new_units": new_units,
            "duplicate_units": duplicate_units,
            "new_count": len(new_units),
            "dup_count": len(duplicate_units),
            "source_type": source_type,
            "source_id": source_id,
        }
