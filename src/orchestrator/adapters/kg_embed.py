"""KG embed adapter: vector embedding for knowledge units."""

import logging
from typing import Any, Dict, Optional

from .base import BaseModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class KGEmbedModule(BaseModule):
    module_name = "kg_embed"

    INPUT_SPEC = {
        "new_units": {"type": "list", "required": True},
        "source_type": {"type": "str", "required": True},
        "source_id": {"type": "str", "required": True},
    }
    OUTPUT_SPEC = {
        "embedded_units": {"type": "list"},
        "embed_count": {"type": "int"},
        "source_type": {"type": "str"},
        "source_id": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.embedder import get_embedder

        new_units = inputs["new_units"]
        source_type = inputs["source_type"]
        source_id = inputs["source_id"]

        embedder_config = self.config.get("embedding")
        embedder = get_embedder(embedder_config)

        embedded_units = []
        for unit in new_units:
            chunk_text = unit.get("text", unit.get("chunk_text", ""))
            abstract_summary = unit.get("abstract_summary", "")

            embedding = await embedder.embed(chunk_text)
            unit["embedding"] = embedding

            if abstract_summary:
                abstract_embedding = await embedder.embed(abstract_summary)
                unit["abstract_embedding"] = abstract_embedding
            else:
                unit["abstract_embedding"] = []

            embedded_units.append(unit)

        await embedder.close()

        logger.info(
            "KGEmbed: embedded %d units from %s/%s",
            len(embedded_units), source_type, source_id,
        )

        return {
            "embedded_units": embedded_units,
            "embed_count": len(embedded_units),
            "source_type": source_type,
            "source_id": source_id,
        }
