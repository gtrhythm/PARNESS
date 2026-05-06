import logging
from typing import Any, Dict, Optional

from ..adapters.base import BaseModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class ExplorationMergeModule(BaseModule):
    module_name: str = "exploration_merge"

    INPUT_SPEC = {
        "explorations": {"type": "list", "required": False, "default": []},
        "refined_ideas": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "saved_explorations": {"type": "int"},
        "refined_ideas": {"type": "list"},
        "total_explorations": {"type": "int"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.db.base import BaseDatabase
        from src.db.writers.knowledge_store_writer import KnowledgeStoreWriter

        explorations = inputs.get("explorations", [])
        refined_ideas = inputs.get("refined_ideas", [])

        db_path = self.config.get("db_path", "output/knowledge_store/knowledge_store.db")

        db = BaseDatabase(db_path)
        writer = KnowledgeStoreWriter(db)
        for exploration in explorations:
            writer.upsert_exploration(
                data=exploration,
                search_queries=exploration.get("search_queries"),
                found_papers=exploration.get("found_papers"),
                found_insights=exploration.get("found_insights"),
                refined_ideas=exploration.get("refined_ideas"),
                references_needed=exploration.get("references_needed"),
                innovation_gaps=exploration.get("innovation_gaps"),
            )
        db.commit()
        db.close()

        return {
            "saved_explorations": len(explorations),
            "refined_ideas": refined_ideas,
            "total_explorations": len(explorations),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        saved = result.get("saved_explorations", 0)
        refined_count = len(result.get("refined_ideas", []))
        return AgentOutput(
            display_type="metrics",
            title="Exploration Merge",
            content=f"Saved {saved} explorations, refined {refined_count} ideas",
            data={
                "saved_explorations": saved,
                "refined_ideas_count": refined_count,
                "total_explorations": result.get("total_explorations", 0),
            },
        )
