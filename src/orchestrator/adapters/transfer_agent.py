import logging
from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class TransferAgentModule(LLMAgentModule):
    module_name = "transfer_agent"

    INPUT_SPEC = {
        "compressed_insights": {"type": "list", "required": False, "default": []},
        "source_domain": {"type": "str", "required": False, "default": ""},
        "target_domain": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "transfer_ideas": {"type": "list"},
        "transfer_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.transfer import TransferAgent
        from src.idea_agents.models import CompressedInsight

        llm_client = self._get_llm_client()

        insights_data = inputs.get("compressed_insights", [])
        if not insights_data:
            return {"transfer_ideas": [], "transfer_count": 0}

        insights = [CompressedInsight.from_dict(d) for d in insights_data]
        source_domain = inputs.get("source_domain", self.config.get("source_domain", ""))
        target_domain = inputs.get("target_domain", self.config.get("target_domain", ""))

        agent = TransferAgent(llm_client)
        transfers = await agent.find_transfers(insights, source_domain, target_domain)

        logger.info("TransferAgentModule: found %d transfer ideas", len(transfers))
        return {
            "transfer_ideas": [t.to_dict() for t in transfers],
            "transfer_count": len(transfers),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        transfers = result.get("transfer_ideas", [])
        if not transfers:
            return None
        rows = [[t.get("method", "")[:40], f"{t.get('source_domain','')}→{t.get('target_domain','')}",
                  str(t.get("feasibility", "")), t.get("rationale", "")[:80]]
                 for t in transfers[:50]]
        return AgentOutput(
            display_type="table",
            title="Cross-Domain Transfer Ideas",
            data={"headers": ["Method", "Source→Target", "Feasibility", "Rationale"], "rows": rows},
            render_hints={"sort_by": 2, "sort_desc": True},
        )
