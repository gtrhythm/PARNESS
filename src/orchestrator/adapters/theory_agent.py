import logging
from typing import Any, Dict, Optional

from ..adapters.base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class TheoryAgentModule(LLMAgentModule):
    module_name: str = "theory_agent"

    INPUT_SPEC = {
        "papers": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "theory_improvements": {"type": "list"},
        "improvement_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.theory import TheoryAgent

        llm_client = self._get_llm_client()

        papers = inputs.get("papers", [])
        if not papers:
            return {"theory_improvements": [], "improvement_count": 0}

        max_concurrent = self.config.get("max_concurrent", 4)
        agent = TheoryAgent(llm_client, max_concurrent=max_concurrent)
        improvements = await agent.analyze_all(papers)

        logger.info("TheoryAgentModule: found %d improvements from %d papers",
                     len(improvements), len(papers))
        return {
            "theory_improvements": [imp.to_dict() for imp in improvements],
            "improvement_count": len(improvements),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        improvements = result.get("theory_improvements", [])
        rows = [[imp.get("paper_title", "")[:60], imp.get("original_assumption", "")[:60],
                  imp.get("issue", "")[:60], imp.get("proposed_correction", "")[:60],
                  imp.get("impact", "")[:60]]
                 for imp in improvements[:50]]
        return AgentOutput(
            display_type="table",
            title="Theoretical Improvements",
            data={"headers": ["Paper", "Original Assumption", "Issue", "Proposed Correction", "Impact"], "rows": rows},
        )
