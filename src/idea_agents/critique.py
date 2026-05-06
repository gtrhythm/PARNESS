import asyncio
import logging
from typing import Dict, List

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, CritiqueItem

logger = logging.getLogger(__name__)

_PROMPT = """You are a rigorous academic reviewer performing deep critique analysis on a paper.

Paper: [{year}] {title}

{content}

Identify specific flaws, weaknesses, and areas for improvement. Return JSON:
{{
  "critiques": [
    {{
      "claim": "The specific claim or assumption being critiqued",
      "flaw": "What is wrong or questionable about this claim",
      "severity": "critical|major|minor",
      "suggested_improvement": "Concrete suggestion to fix or improve",
      "evidence": "Why this is a valid critique (evidence or reasoning)"
    }}
  ]
}}

Rules:
- Every critique must reference a SPECIFIC claim from the paper
- Severity: critical = undermines main conclusion, major = significant limitation, minor = small issue
- Suggested improvements must be actionable
- Do not nitpick writing style; focus on methodology, assumptions, and claims
"""


class CritiqueAgent:
    def __init__(self, llm_client, max_concurrent: int = 4):
        self.llm = llm_client
        self.max_concurrent = max_concurrent

    async def critique_all(self, papers: List[Dict]) -> List[CritiqueItem]:
        sem = asyncio.Semaphore(self.max_concurrent)
        results = []

        async def _critique_one(paper: Dict):
            async with sem:
                try:
                    critiques = await self.critique(paper)
                    results.extend(critiques)
                except Exception as e:
                    logger.warning("CritiqueAgent failed for %s: %s",
                                   paper.get("paper_id", "?"), e)

        await asyncio.gather(*[_critique_one(p) for p in papers])
        logger.info("CritiqueAgent: found %d critiques from %d papers",
                     len(results), len(papers))
        return results

    async def critique(self, paper: Dict) -> List[CritiqueItem]:
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
            CritiqueItem(
                paper_id=paper_id,
                claim=c.get("claim", ""),
                flaw=c.get("flaw", ""),
                severity=c.get("severity", "minor"),
                suggested_improvement=c.get("suggested_improvement", ""),
                evidence=c.get("evidence", ""),
            )
            for c in data.get("critiques", [])
        ]
