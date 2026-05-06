import logging
from typing import Any, Dict, Optional

from ..adapters.base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class LimitationAgentModule(LLMAgentModule):
    module_name: str = "limitation_agent"

    INPUT_SPEC = {
        "papers": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "limitation_extensions": {"type": "list"},
        "extension_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.limitation import LimitationAgent

        llm_client = self._get_llm_client()

        papers = inputs.get("papers", [])
        if not papers:
            return {"limitation_extensions": [], "extension_count": 0}

        max_concurrent = self.config.get("max_concurrent", 4)
        agent = LimitationAgent(llm_client, max_concurrent=max_concurrent)
        extensions = await agent.analyze_all(papers)

        logger.info("LimitationAgentModule: found %d extensions from %d papers",
                     len(extensions), len(papers))
        return {
            "limitation_extensions": [e.to_dict() for e in extensions],
            "extension_count": len(extensions),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        extensions = result.get("limitation_extensions", [])
        rows = [[e.get("paper_title", "")[:60], e.get("stated_limitation", "")[:60],
                  e.get("extension_direction", "")[:60], e.get("proposed_approach", "")[:60],
                  e.get("difficulty", "")]
                 for e in extensions[:50]]
        return AgentOutput(
            display_type="table",
            title="Limitation Extensions",
            data={"headers": ["Paper", "Stated Limitation", "Extension Direction", "Proposed Approach", "Difficulty"], "rows": rows},
            render_hints={"difficulty_colors": {"easy": "green", "medium": "yellow", "hard": "orange", "very_hard": "red"}},
        )
