"""KG extract adapter: LLM-powered knowledge unit extraction."""

import logging
from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class KGExtractModule(LLMAgentModule):
    module_name = "kg_extract"

    INPUT_SPEC = {
        "content": {"type": "str", "required": True},
        "source_type": {"type": "str", "required": True},
        "source_id": {"type": "str", "required": True},
        "surrounding_context": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "units": {"type": "list"},
        "unit_count": {"type": "int"},
        "source_type": {"type": "str"},
        "source_id": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.chunker import KGChunker

        llm_client = self._get_llm_client()
        content = inputs["content"]
        source_type = inputs["source_type"]
        source_id = inputs["source_id"]
        surrounding_context = inputs.get("surrounding_context", "")

        chunker = KGChunker()
        units = await chunker.extract_units(
            llm_client, content, source_type, source_id, surrounding_context
        )

        unit_dicts = [u.to_dict() for u in units]

        logger.info("KGExtract: extracted %d units from %s/%s", len(unit_dicts), source_type, source_id)

        return {
            "units": unit_dicts,
            "unit_count": len(unit_dicts),
            "source_type": source_type,
            "source_id": source_id,
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        unit_count = result.get("unit_count", 0)
        return AgentOutput(
            display_type="metrics",
            title="KG Extract",
            content=f"Extracted {unit_count} units",
            data={"unit_count": unit_count},
        )
