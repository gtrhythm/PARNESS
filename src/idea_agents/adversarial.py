import asyncio
import logging
from typing import Dict, List

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, FailureCase

logger = logging.getLogger(__name__)

_PROMPT = """You are an adversarial researcher whose job is to find failure cases and break papers' claims.

Paper: [{year}] {title}

{content}

Perform an adversarial analysis. Find scenarios where this paper's method would FAIL. Return JSON:
{{
  "failure_cases": [
    {{
      "method_description": "The specific method/technique being challenged",
      "failure_scenario": "A concrete scenario where the method fails",
      "why_it_fails": "The underlying reason for failure",
      "counter_example": "A specific example or construction that demonstrates the failure",
      "suggested_fix": "How to make the method robust to this failure case"
    }}
  ]
}}

Rules:
- Think like an adversary: actively try to break the method, not just find minor issues
- Failure scenarios should be realistic and practically relevant
- Counter-examples should be specific enough to be testable
- Every failure case must come with a constructive fix suggestion
- Focus on the CORE method, not peripheral details
"""


class AdversarialAgent:
    def __init__(self, llm_client, max_concurrent: int = 4):
        self.llm = llm_client
        self.max_concurrent = max_concurrent

    async def attack_all(self, papers: List[Dict]) -> List[FailureCase]:
        sem = asyncio.Semaphore(self.max_concurrent)
        results = []

        async def _attack_one(paper: Dict):
            async with sem:
                try:
                    cases = await self.attack(paper)
                    results.extend(cases)
                except Exception as e:
                    logger.warning("AdversarialAgent failed for %s: %s",
                                   paper.get("paper_id", "?"), e)

        await asyncio.gather(*[_attack_one(p) for p in papers])
        logger.info("AdversarialAgent: found %d failure cases from %d papers",
                     len(results), len(papers))
        return results

    async def attack(self, paper: Dict) -> List[FailureCase]:
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
            FailureCase(
                paper_id=paper_id,
                paper_title=title,
                method_description=fc.get("method_description", ""),
                failure_scenario=fc.get("failure_scenario", ""),
                why_it_fails=fc.get("why_it_fails", ""),
                counter_example=fc.get("counter_example", ""),
                suggested_fix=fc.get("suggested_fix", ""),
            )
            for fc in data.get("failure_cases", [])
        ]
