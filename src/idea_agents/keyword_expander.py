import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from .llm_utils import call_llm, parse_json_response

logger = logging.getLogger(__name__)

_PROMPT = """You are a research keyword expansion agent. Your job is to take a research direction and expand it into structured search queries, keywords, sub-topics, and related terms for academic literature search.

Research Direction: {direction_name}
{description_block}

Return JSON:
{{
  "keywords": ["keyword1", "keyword2", "..."],
  "sub_topics": ["sub topic 1", "..."],
  "arxiv_categories": ["cs.CL", "..."],
  "semantic_scholar_queries": ["query1", "..."],
  "arxiv_queries": ["ti:xxx AND abs:xxx", "..."],
  "related_terms": ["synonym1", "..."],
  "research_threads": ["thread description", "..."],
  "expanded_direction": {{
    "name": "...",
    "description": "expanded 2-3 sentence description",
    "keywords": [...],
    "sub_topics": [...],
    "depth": "explore"
  }}
}}

Rules:
- Keywords: 8-15 core technical keywords in English, academic terminology. Include both broad terms and specific technical terms.
- sub_topics: 3-6 specific research sub-directions representing distinct research angles within the direction.
- arxiv_categories: suggested arxiv categories relevant to this direction.
- semantic_scholar_queries: 5-8 natural language phrases suitable for paper search.
- arxiv_queries: 3-5 structured queries using arXiv API syntax: ti: (title), abs: (abstract), cat: (category), AND, OR.
- related_terms: related/synonym terms that could help broaden or refine search.
- research_threads: 3-5 descriptions of active lines of investigation in this area.
- expanded_direction: a filled object with name, a 2-3 sentence expanded description, a subset of the top keywords, a subset of the sub_topics, and depth set to "explore".
"""


@dataclass
class ExpandedDirection:
    keywords: List[str] = field(default_factory=list)
    sub_topics: List[str] = field(default_factory=list)
    arxiv_categories: List[str] = field(default_factory=list)
    semantic_scholar_queries: List[str] = field(default_factory=list)
    arxiv_queries: List[str] = field(default_factory=list)
    related_terms: List[str] = field(default_factory=list)
    research_threads: List[str] = field(default_factory=list)
    expanded_direction: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class KeywordExpander:
    def __init__(self, llm_client):
        self.llm = llm_client

    async def expand(self, direction_name: str, direction_description: str = "") -> ExpandedDirection:
        description_block = f"Description: {direction_description}" if direction_description else ""
        prompt = _PROMPT.format(
            direction_name=direction_name,
            description_block=description_block,
        )

        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        result = ExpandedDirection(
            keywords=data.get("keywords", []),
            sub_topics=data.get("sub_topics", []),
            arxiv_categories=data.get("arxiv_categories", []),
            semantic_scholar_queries=data.get("semantic_scholar_queries", []),
            arxiv_queries=data.get("arxiv_queries", []),
            related_terms=data.get("related_terms", []),
            research_threads=data.get("research_threads", []),
            expanded_direction=data.get("expanded_direction", {}),
        )

        logger.info(
            "KeywordExpander: expanded '%s' into %d keywords, %d sub_topics, %d queries",
            direction_name,
            len(result.keywords),
            len(result.sub_topics),
            len(result.semantic_scholar_queries),
        )

        return result
