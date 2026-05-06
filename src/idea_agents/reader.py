import asyncio
import logging
from typing import Dict, List

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, ResearchDirection

logger = logging.getLogger(__name__)

_PROMPT = """You are a senior researcher skimming a paper. Compress it into structured insights.

Paper: [{year}] {title}

{content}

Extract in JSON:
{{
  "core_insight": "ONE sentence: the deepest insight/contribution",
  "problem_solved": "ONE sentence: what problem it solves",
  "key_trick": "ONE sentence: the key technical trick",
  "limitations": ["limitation 1", "limitation 2"],
  "open_questions": ["question this paper raises"],
  "reusable_components": ["technique that could be reused elsewhere"],
  "assumed_but_not_proven": ["assumption the authors make but don't verify"]
}}

Rules:
- Each field should be concise (1-2 sentences max per item)
- limitations/open_questions are the most important fields for downstream ideation
- Be specific, not generic ("assumes static graph structure" not "has limitations")
"""


class ReaderAgent:
    def __init__(self, llm_client, max_concurrent: int = 4, budget=None):
        self.llm = llm_client
        self.max_concurrent = max_concurrent
        self.budget = budget

    async def read_all(self, papers: List[Dict]) -> List[CompressedInsight]:
        sem = asyncio.Semaphore(self.max_concurrent)
        results = []

        async def _read_one(paper: Dict):
            async with sem:
                try:
                    insight = await self.read(paper)
                    if insight and insight.core_insight:
                        results.append(insight)
                except Exception as e:
                    logger.warning("Reader failed for %s: %s", paper.get("paper_id", "?"), e)

        await asyncio.gather(*[_read_one(p) for p in papers])
        logger.info("Reader: compressed %d/%d papers", len(results), len(papers))
        return results

    def _content_budget(self) -> int:
        if self.budget:
            return int(self.budget.max_context * 0.4)
        return 3000

    async def read(self, paper: Dict, direction: ResearchDirection = None) -> CompressedInsight:
        title = paper.get("metadata", {}).get("title", paper.get("title", ""))
        year = paper.get("metadata", {}).get("year", paper.get("year", 0))
        paper_id = paper.get("paper_id", "")

        content = paper.get("full_text", "")
        if not content:
            content = paper.get("abstract", "")
        if not content:
            content = paper.get("metadata", {}).get("abstract", "")
        if not content or len(content) < 30:
            return None

        direction_text = ""
        if direction:
            direction_text = f"\n{direction.prompt_block()}\nFocus your analysis on this specific research direction.\n"

        prompt = _PROMPT.format(
            year=year, title=title,
            content=content[:self._content_budget()] + direction_text,
        )

        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        return CompressedInsight(
            paper_id=paper_id,
            title=title,
            year=year,
            core_insight=data.get("core_insight", ""),
            problem_solved=data.get("problem_solved", ""),
            key_trick=data.get("key_trick", ""),
            limitations=data.get("limitations", []),
            open_questions=data.get("open_questions", []),
            reusable_components=data.get("reusable_components", []),
            assumed_but_not_proven=data.get("assumed_but_not_proven", []),
        )
