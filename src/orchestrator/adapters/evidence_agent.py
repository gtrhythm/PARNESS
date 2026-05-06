import logging
from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class EvidenceAgentModule(LLMAgentModule):
    module_name = "evidence_agent"

    INPUT_SPEC = {
        "hypotheses": {"type": "list", "required": False, "default": []},
        "compressed_insights": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "evidence_items": {"type": "list"},
        "evidence_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.evidence import EvidenceAgent
        from src.idea_agents.models import CompressedInsight, Hypothesis

        llm_client = self._get_llm_client()

        hypotheses_data = inputs.get("hypotheses", [])
        insights_data = inputs.get("compressed_insights", [])
        if not hypotheses_data or not insights_data:
            return {"evidence_items": [], "evidence_count": 0}

        hypotheses = [Hypothesis.from_dict(d) for d in hypotheses_data]
        insights = [CompressedInsight.from_dict(d) for d in insights_data]

        max_concurrent = self.config.get("max_concurrent", 4)
        agent = EvidenceAgent(llm_client, max_concurrent=max_concurrent)
        evidence = await agent.collect_evidence(hypotheses, insights)

        logger.info("EvidenceAgentModule: collected %d evidence items", len(evidence))
        return {
            "evidence_items": [e.to_dict() for e in evidence],
            "evidence_count": len(evidence),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        evidence = result.get("evidence_items", [])
        if not evidence:
            return None
        evidence_data = [{
            "hypothesis_id": e.get("hypothesis_id", ""),
            "paper_title": e.get("paper_title", "")[:80],
            "stance": e.get("stance", ""),
            "strength": e.get("strength", ""),
            "relevance": e.get("relevance", ""),
        } for e in evidence]
        stance_counts = {"supporting": 0, "refuting": 0, "mixed": 0, "neutral": 0}
        for e in evidence:
            stance = e.get("stance", "").lower()
            if stance in stance_counts:
                stance_counts[stance] += 1
        return AgentOutput(
            display_type="table",
            title="Evidence Collection Results",
            data={"evidence": evidence_data, "stance_summary": stance_counts},
            render_hints={"stance_colors": {"supporting": "green", "refuting": "red", "mixed": "yellow", "neutral": "gray"},
                          "group_by": "hypothesis_id"},
        )
