import logging
from typing import Any, Dict, List, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class ReaderAgentModule(LLMAgentModule):
    module_name = "reader_agent"

    INPUT_SPEC = {
        "papers": {"type": "list", "required": False, "default": []},
        "existing_paper_ids": {"type": "list", "required": False, "default": []},
        "existing_insights": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "compressed_insights": {"type": "list"},
        "new_insight_count": {"type": "int"},
        "insight_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.reader import ReaderAgent
        from src.idea_agents.token_budget import PromptBudget

        papers = inputs.get("papers", [])
        existing_ids = set(inputs.get("existing_paper_ids", []))
        new_papers = [p for p in papers if p.get("paper_id", "") not in existing_ids]
        if not existing_ids:
            new_papers = papers
        existing_insights = inputs.get("existing_insights", [])

        llm_client = self._get_llm_client()

        if not new_papers:
            logger.info("Reader: no new papers to read")
            return {
                "compressed_insights": existing_insights,
                "new_insight_count": 0,
                "insight_count": len(existing_insights),
            }

        max_concurrent = self.config.get("max_concurrent", 4)
        budget = PromptBudget.from_config(self.config)
        agent = ReaderAgent(llm_client, max_concurrent=max_concurrent, budget=budget)
        new_insights = await agent.read_all(new_papers)

        all_insights = list(existing_insights)
        new_ids = set()
        for i in new_insights:
            d = i.to_dict()
            if i.paper_id not in new_ids:
                new_ids.add(i.paper_id)
                all_insights.append(d)

        logger.info("Reader: %d new + %d existing = %d total insights",
                     len(new_insights), len(existing_insights),
                     len(all_insights))

        return {
            "compressed_insights": all_insights,
            "new_insight_count": len(new_insights),
            "insight_count": len(all_insights),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        if "new_insight_count" not in result:
            return None
        rows = []
        for i in result["compressed_insights"][:50]:
            rows.append([
                i.get("title", i.get("paper_title", ""))[:60],
                str(i.get("year", "")),
                i.get("core_insight", "")[:100],
                i.get("key_trick", "")[:60],
                i.get("limitations", "")[:60],
            ])
        return AgentOutput(
            display_type="table",
            title="Extracted Paper Insights",
            data={"headers": ["Paper", "Year", "Core Insight", "Key Trick", "Limitations"], "rows": rows},
            render_hints={"max_col_width": [30, 6, 60, 40, 40], "sort_by": 1, "sort_desc": True},
        )
