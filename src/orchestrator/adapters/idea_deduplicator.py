import logging
from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class IdeaDeduplicatorModule(LLMAgentModule):
    module_name = "idea_deduplicator"

    INPUT_SPEC = {
        "ideas": {"type": "list", "required": False, "default": []},
        "existing_ideas": {"type": "list", "required": False, "default": []},
        "similarity_threshold": {"type": "float", "required": False, "default": 0.85},
    }
    OUTPUT_SPEC = {
        "unique_ideas": {"type": "list"},
        "duplicate_count": {"type": "int"},
        "duplicate_pairs": {"type": "list"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_deduplicator.deduplicator import IdeaDeduplicator

        ideas = inputs.get("ideas", [])
        existing = inputs.get("existing_ideas", [])

        if not ideas:
            return {
                "unique_ideas": [],
                "duplicate_count": 0,
                "_input_count": 0,
                "_existing_count": len(existing),
            }

        threshold = inputs.get("similarity_threshold", self.config.get("similarity_threshold", 0.85))

        llm_client = self.config.get("llm_client")
        dedup = IdeaDeduplicator(llm_client=llm_client, similarity_threshold=threshold)
        unique, duplicates = await dedup.deduplicate(ideas, existing)

        return {
            "unique_ideas": unique,
            "duplicate_count": len(duplicates),
            "duplicate_pairs": [
                {"idea_a": a.get("title", ""), "idea_b": b.get("title", ""), "similarity": round(s, 3)}
                for a, b, s in duplicates
            ],
            "_input_count": len(ideas),
            "_existing_count": len(existing),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        input_count = result.get("_input_count", 0)
        existing_count = result.get("_existing_count", 0)
        unique_ideas = result.get("unique_ideas", [])
        duplicate_count = result.get("duplicate_count", 0)
        return AgentOutput(
            display_type="metrics",
            title="Idea Deduplication",
            content=f"{len(unique_ideas)} unique ideas, {duplicate_count} duplicates found",
            data={"input_count": input_count, "existing_count": existing_count,
                  "unique_count": len(unique_ideas), "duplicate_count": duplicate_count,
                  "duplicate_pairs": result.get("duplicate_pairs", [])},
            render_hints={"highlight": "duplicate_count", "warning_threshold": 5, "show_pairs": True},
        )
