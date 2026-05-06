import logging
from typing import Any, Dict, Optional

from ..adapters.base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class CritiqueAgentModule(LLMAgentModule):
    module_name: str = "critique_agent"

    INPUT_SPEC = {
        "papers": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "critiques": {"type": "list"},
        "critique_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.critique import CritiqueAgent

        llm_client = self._get_llm_client()

        papers = inputs.get("papers", [])
        if not papers:
            return {"critiques": [], "critique_count": 0}

        max_concurrent = self.config.get("max_concurrent", 4)
        agent = CritiqueAgent(llm_client, max_concurrent=max_concurrent)
        critiques = await agent.critique_all(papers)

        logger.info("CritiqueAgentModule: found %d critiques from %d papers",
                     len(critiques), len(papers))
        return {
            "critiques": [c.to_dict() for c in critiques],
            "critique_count": len(critiques),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        critiques = result.get("critiques", [])
        rows = [[c.get("paper_title", "")[:60], c.get("claim", "")[:60],
                  c.get("flaw", "")[:60], c.get("severity", ""),
                  c.get("suggested_fix", "")[:60]]
                 for c in critiques[:50]]
        return AgentOutput(
            display_type="table",
            title="Paper Critiques",
            data={"headers": ["Paper", "Claim", "Flaw", "Severity", "Suggested Fix"], "rows": rows},
            render_hints={"severity_colors": {"critical": "red", "major": "orange", "minor": "yellow"}},
        )
