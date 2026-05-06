import asyncio
import logging
from typing import Dict, List

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, LimitationExtension

logger = logging.getLogger(__name__)

_PROMPT = """You are a researcher who specializes in reading papers' stated limitations and turning them into concrete research directions.

Paper: [{year}] {title}

{content}

Extract every stated limitation, weakness, or future work direction, and turn each into a concrete research extension. Return JSON:
{{
  "extensions": [
    {{
      "stated_limitation": "The exact limitation or future work direction stated in the paper",
      "extension_direction": "A concrete research direction to address this limitation",
      "proposed_approach": "Specific methodology or approach to tackle it",
      "expected_contribution": "What new knowledge or capability would result",
      "difficulty": "easy|medium|hard - estimated difficulty of pursuing this"
    }}
  ]
}}

Rules:
- Start from the paper's OWN stated limitations (in the limitations/future work section)
- Each extension should transform a limitation into an actionable research project
- The proposed approach must be specific enough for a graduate student to start working on
- Expected contribution should explain what the field gains
- Difficulty should account for data availability, compute needs, and technical complexity
"""


class LimitationAgent:
    def __init__(self, llm_client, max_concurrent: int = 4):
        self.llm = llm_client
        self.max_concurrent = max_concurrent

    async def analyze_all(self, papers: List[Dict]) -> List[LimitationExtension]:
        sem = asyncio.Semaphore(self.max_concurrent)
        results = []

        async def _analyze_one(paper: Dict):
            async with sem:
                try:
                    extensions = await self.analyze(paper)
                    results.extend(extensions)
                except Exception as e:
                    logger.warning("LimitationAgent failed for %s: %s",
                                   paper.get("paper_id", "?"), e)

        await asyncio.gather(*[_analyze_one(p) for p in papers])
        logger.info("LimitationAgent: found %d extensions from %d papers",
                     len(results), len(papers))
        return results

    async def analyze(self, paper: Dict) -> List[LimitationExtension]:
        title = paper.get("metadata", {}).get("title", paper.get("title", ""))
        year = paper.get("metadata", {}).get("year", paper.get("year", 0))
        paper_id = paper.get("paper_id", "")

        content = paper.get("full_text", "") or paper.get("abstract", "") or \
            paper.get("metadata", {}).get("abstract", "")
        if not content or len(content) < 30:
            return []

        prompt = _PROMPT.format(year=year, title=title, content=content[:4000])
        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        return [
            LimitationExtension(
                paper_id=paper_id,
                paper_title=title,
                stated_limitation=ext.get("stated_limitation", ""),
                extension_direction=ext.get("extension_direction", ""),
                proposed_approach=ext.get("proposed_approach", ""),
                expected_contribution=ext.get("expected_contribution", ""),
                difficulty=ext.get("difficulty", ""),
            )
            for ext in data.get("extensions", [])
        ]
