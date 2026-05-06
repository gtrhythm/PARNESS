import logging
from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class KeywordExpanderModule(LLMAgentModule):
    module_name = "keyword_expander"

    INPUT_SPEC = {
        "direction_name": {"type": "str", "required": True},
        "direction_description": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "keywords": {"type": "list"},
        "sub_topics": {"type": "list"},
        "arxiv_categories": {"type": "list"},
        "semantic_scholar_queries": {"type": "list"},
        "arxiv_queries": {"type": "list"},
        "related_terms": {"type": "list"},
        "research_threads": {"type": "list"},
        "expanded_direction": {"type": "dict"},
        "_direction_name": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.keyword_expander import KeywordExpander

        llm_client = self._get_llm_client()

        direction_name = inputs.get("direction_name", "")
        direction_description = inputs.get("direction_description", "")

        if not direction_name:
            raise ValueError("'direction_name' is required")

        agent = KeywordExpander(llm_client)
        result = await agent.expand(direction_name, direction_description)

        return {
            "keywords": result.keywords,
            "sub_topics": result.sub_topics,
            "arxiv_categories": result.arxiv_categories,
            "semantic_scholar_queries": result.semantic_scholar_queries,
            "arxiv_queries": result.arxiv_queries,
            "related_terms": result.related_terms,
            "research_threads": result.research_threads,
            "expanded_direction": result.expanded_direction,
            "_direction_name": direction_name,
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        direction_name = result.get("_direction_name", "")
        return AgentOutput(
            display_type="list",
            title="Keyword Expansion",
            data={"direction": direction_name, "keywords": result.get("keywords", []),
                  "sub_topics": result.get("sub_topics", []),
                  "semantic_scholar_queries": result.get("semantic_scholar_queries", []),
                  "arxiv_queries": result.get("arxiv_queries", []),
                  "arxiv_categories": result.get("arxiv_categories", []),
                  "related_terms": result.get("related_terms", []),
                  "research_threads": result.get("research_threads", [])},
            render_hints={"group_by": ["keywords", "sub_topics", "queries", "research_threads"], "collapsible": True},
        )
