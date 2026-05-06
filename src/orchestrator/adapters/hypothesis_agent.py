import logging
from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class HypothesisAgentModule(LLMAgentModule):
    module_name = "hypothesis_agent"

    INPUT_SPEC = {
        "compressed_insights": {"type": "list", "required": False, "default": []},
        "context": {"type": "str", "required": False, "default": ""},
        "max_hypotheses": {"type": "int", "required": False, "default": 10},
    }
    OUTPUT_SPEC = {
        "hypotheses": {"type": "list"},
        "hypothesis_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.hypothesis import HypothesisAgent
        from src.idea_agents.models import CompressedInsight

        llm_client = self._get_llm_client()

        insights_data = inputs.get("compressed_insights", [])
        if not insights_data:
            return {"hypotheses": [], "hypothesis_count": 0}

        insights = [CompressedInsight.from_dict(d) for d in insights_data]
        context = inputs.get("context", self.config.get("context", ""))
        max_hypotheses = inputs.get("max_hypotheses", self.config.get("max_hypotheses", 10))

        agent = HypothesisAgent(llm_client)
        hypotheses = await agent.generate(insights, context=context,
                                          max_hypotheses=max_hypotheses)

        logger.info("HypothesisAgentModule: generated %d hypotheses", len(hypotheses))
        return {
            "hypotheses": [h.to_dict() for h in hypotheses],
            "hypothesis_count": len(hypotheses),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        hypotheses = result.get("hypotheses", [])
        if not hypotheses:
            return None
        hypotheses_data = [{
            "statement": h.get("statement", "")[:100],
            "confidence": h.get("confidence", 0),
            "testability": h.get("testability", ""),
            "predicted_outcome": h.get("predicted_outcome", "")[:80],
            "source_papers": h.get("source_papers", []),
        } for h in hypotheses]
        return AgentOutput(
            display_type="table",
            title="Generated Research Hypotheses",
            data={"hypotheses": hypotheses_data},
            render_hints={"sort_by": "confidence", "sort_desc": True},
        )
