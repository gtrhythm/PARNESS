import logging
from typing import Any, Dict, Optional

from ..adapters.base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class AdversarialAgentModule(LLMAgentModule):
    module_name: str = "adversarial_agent"

    INPUT_SPEC = {
        "papers": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "failure_cases": {"type": "list"},
        "failure_case_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.adversarial import AdversarialAgent

        llm_client = self._get_llm_client()

        papers = inputs.get("papers", [])
        if not papers:
            return {"failure_cases": [], "failure_case_count": 0}

        max_concurrent = self.config.get("max_concurrent", 4)
        agent = AdversarialAgent(llm_client, max_concurrent=max_concurrent)
        cases = await agent.attack_all(papers)

        logger.info("AdversarialAgentModule: found %d failure cases from %d papers",
                     len(cases), len(papers))
        return {
            "failure_cases": [c.to_dict() for c in cases],
            "failure_case_count": len(cases),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        cases = result.get("failure_cases", [])
        rows = [[c.get("paper_title", "")[:60], c.get("method", "")[:60],
                  c.get("failure_scenario", "")[:60], c.get("why_it_fails", "")[:60],
                  c.get("suggested_fix", "")[:60]]
                 for c in cases[:50]]
        return AgentOutput(
            display_type="table",
            title="Adversarial Failure Cases",
            data={"headers": ["Paper", "Method", "Failure Scenario", "Why It Fails", "Suggested Fix"], "rows": rows},
        )
