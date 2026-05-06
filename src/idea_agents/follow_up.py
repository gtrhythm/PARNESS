import asyncio
import logging
from typing import Dict, List

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, FollowUpIdea

logger = logging.getLogger(__name__)

_PROMPT = """You are a researcher tracking cutting-edge work and identifying fast follow-up opportunities.

Paper: [{year}] {title}

{content}

Extract the future work directions and generate concrete follow-up research ideas. Return JSON:
{{
  "follow_ups": [
    {{
      "future_work_claim": "What the paper says about future directions (direct quote or paraphrase)",
      "extension_idea": "A concrete, novel research idea extending this work",
      "feasibility": "high|medium|low - how feasible to execute this in 1-3 months",
      "novelty_assessment": "Why this extension would be novel",
      "required_resources": "What resources/datasets/compute are needed"
    }}
  ]
}}

Rules:
- Extract explicit future work claims from the paper
- Transform each future work claim into a concrete, actionable research idea
- The extension should go BEYOND what the paper suggests, adding your own insight
- Feasibility should consider typical academic resources
- Be specific about what makes the extension novel vs. incremental
"""


class FollowUpAgent:
    def __init__(self, llm_client, max_concurrent: int = 4):
        self.llm = llm_client
        self.max_concurrent = max_concurrent

    async def analyze_all(self, papers: List[Dict]) -> List[FollowUpIdea]:
        sem = asyncio.Semaphore(self.max_concurrent)
        results = []

        async def _analyze_one(paper: Dict):
            async with sem:
                try:
                    follow_ups = await self.analyze(paper)
                    results.extend(follow_ups)
                except Exception as e:
                    logger.warning("FollowUpAgent failed for %s: %s",
                                   paper.get("paper_id", "?"), e)

        await asyncio.gather(*[_analyze_one(p) for p in papers])
        logger.info("FollowUpAgent: found %d follow-up ideas from %d papers",
                     len(results), len(papers))
        return results

    async def analyze(self, paper: Dict) -> List[FollowUpIdea]:
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
            FollowUpIdea(
                original_paper_id=paper_id,
                original_paper_title=title,
                future_work_claim=f.get("future_work_claim", ""),
                extension_idea=f.get("extension_idea", ""),
                feasibility=f.get("feasibility", ""),
                novelty_assessment=f.get("novelty_assessment", ""),
                required_resources=f.get("required_resources", ""),
            )
            for f in data.get("follow_ups", [])
        ]
