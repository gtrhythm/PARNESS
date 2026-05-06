import logging
from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class ReplicationAgentModule(LLMAgentModule):
    module_name = "replication_agent"

    INPUT_SPEC = {
        "papers": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "replication_problems": {"type": "list"},
        "problem_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.replication import ReplicationAgent

        llm_client = self._get_llm_client()

        papers = inputs.get("papers", [])
        if not papers:
            return {"replication_problems": [], "problem_count": 0}

        max_concurrent = self.config.get("max_concurrent", 4)
        agent = ReplicationAgent(llm_client, max_concurrent=max_concurrent)
        problems = await agent.analyze_all(papers)

        logger.info("ReplicationAgentModule: found %d problems from %d papers",
                     len(problems), len(papers))
        return {
            "replication_problems": [p.to_dict() for p in problems],
            "problem_count": len(problems),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        problems = result.get("replication_problems", [])
        if not problems:
            return None
        rows = [[p.get("paper_title", "")[:60], p.get("claimed_result", "")[:60],
                  p.get("reproduction_issue", "")[:60], p.get("suggested_experiment", "")[:60]]
                 for p in problems[:50]]
        return AgentOutput(
            display_type="table",
            title="Replication Opportunities",
            data={"headers": ["Paper", "Claimed Result", "Reproduction Issue", "Suggested Experiment"], "rows": rows},
        )
