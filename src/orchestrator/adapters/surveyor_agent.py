import logging
from typing import Any, Dict, Optional

from ..adapters.base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class SurveyorAgentModule(LLMAgentModule):
    module_name: str = "surveyor_agent"

    INPUT_SPEC = {
        "papers": {"type": "list", "required": False, "default": []},
        "direction": {"type": "dict", "required": False, "default": None},
    }
    OUTPUT_SPEC = {
        "literature_survey": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.surveyor import SurveyorAgent
        from src.idea_agents.models import ResearchDirection

        llm_client = self._get_llm_client()

        papers = inputs.get("papers", [])
        direction_data = inputs.get("direction")
        direction = ResearchDirection.from_dict(direction_data) if direction_data else None
        agent = SurveyorAgent(llm_client)
        result = await agent.survey(papers, direction)

        return {"literature_survey": result.to_dict()}

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        survey_dict = result.get("literature_survey", {})
        md_lines = ["# Literature Survey\n"]
        if survey_dict.get("summary"):
            md_lines.append(f"\n## Summary\n{survey_dict['summary']}\n")
        if survey_dict.get("key_papers"):
            md_lines.append("\n## Key Papers\n")
            for p in survey_dict["key_papers"]:
                md_lines.append(f"- {p}\n")
        if survey_dict.get("research_threads"):
            md_lines.append("\n## Research Threads\n")
            for t in survey_dict["research_threads"]:
                md_lines.append(f"- {t}\n")
        if survey_dict.get("open_problems"):
            md_lines.append("\n## Open Problems\n")
            for o in survey_dict["open_problems"]:
                md_lines.append(f"- {o}\n")
        if survey_dict.get("trends"):
            md_lines.append("\n## Trends\n")
            for t in survey_dict["trends"]:
                md_lines.append(f"- {t}\n")
        return AgentOutput(
            display_type="markdown",
            title="Literature Survey",
            content="".join(md_lines),
        )
