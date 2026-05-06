import asyncio
import logging
from typing import Dict, List

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, TheoryImprovement

logger = logging.getLogger(__name__)

_PROMPT = """You are a theoretical researcher skilled at finding mathematical and theoretical issues in papers.

Paper: [{year}] {title}

{content}

Analyze the theoretical foundations of this paper. Identify theoretical weaknesses, unproven assumptions, or opportunities for theoretical improvement. Return JSON:
{{
  "improvements": [
    {{
      "original_assumption": "The assumption or theorem being questioned",
      "theoretical_issue": "What is theoretically problematic",
      "proposed_correction": "A proposed fix or stronger result",
      "mathematical_sketch": "Brief sketch of the corrected/improved approach",
      "impact_assessment": "How this change would affect the paper's conclusions"
    }}
  ]
}}

Rules:
- Focus on mathematical rigor: missing proofs, incorrect bounds, hidden assumptions
- Propose concrete theoretical corrections, not just "this needs more analysis"
- Mathematical sketch should include key formulas or proof strategy
- Assess impact honestly: some fixes may strengthen, others may weaken conclusions
"""


class TheoryAgent:
    def __init__(self, llm_client, max_concurrent: int = 4):
        self.llm = llm_client
        self.max_concurrent = max_concurrent

    async def analyze_all(self, papers: List[Dict]) -> List[TheoryImprovement]:
        sem = asyncio.Semaphore(self.max_concurrent)
        results = []

        async def _analyze_one(paper: Dict):
            async with sem:
                try:
                    improvements = await self.analyze(paper)
                    results.extend(improvements)
                except Exception as e:
                    logger.warning("TheoryAgent failed for %s: %s",
                                   paper.get("paper_id", "?"), e)

        await asyncio.gather(*[_analyze_one(p) for p in papers])
        logger.info("TheoryAgent: found %d improvements from %d papers",
                     len(results), len(papers))
        return results

    async def analyze(self, paper: Dict) -> List[TheoryImprovement]:
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
            TheoryImprovement(
                paper_id=paper_id,
                original_assumption=imp.get("original_assumption", ""),
                theoretical_issue=imp.get("theoretical_issue", ""),
                proposed_correction=imp.get("proposed_correction", ""),
                mathematical_sketch=imp.get("mathematical_sketch", ""),
                impact_assessment=imp.get("impact_assessment", ""),
            )
            for imp in data.get("improvements", [])
        ]
