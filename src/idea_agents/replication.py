import asyncio
import logging
from typing import Dict, List

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, ReplicationProblem

logger = logging.getLogger(__name__)

_PROMPT = """You are an expert researcher analyzing a paper for reproducibility issues and hidden problems.

Paper: [{year}] {title}

{content}

Analyze this paper for potential replication and reproduction problems. Return JSON:
{{
  "claimed_result": "The main claimed result in one sentence",
  "reproduction_issues": [
    {{
      "issue": "What specific detail is missing or ambiguous",
      "impact": "How this affects reproducibility"
    }}
  ],
  "missing_details": ["list of missing implementation details"],
  "suggested_experiments": [
    "experiment to verify/replicate the key claim"
  ],
  "potential_improvements": [
    "how to fix the identified issues"
  ]
}}

Rules:
- Focus on concrete, specific problems, not generic complaints
- Identify missing hyperparameters, unclear procedures, unstated assumptions
- Suggest experiments that could reveal if the results hold
- Be constructive: every problem should come with a suggested improvement
"""


class ReplicationAgent:
    def __init__(self, llm_client, max_concurrent: int = 4):
        self.llm = llm_client
        self.max_concurrent = max_concurrent

    async def analyze_all(self, papers: List[Dict]) -> List[ReplicationProblem]:
        sem = asyncio.Semaphore(self.max_concurrent)
        results = []

        async def _analyze_one(paper: Dict):
            async with sem:
                try:
                    problem = await self.analyze(paper)
                    if problem:
                        results.append(problem)
                except Exception as e:
                    logger.warning("ReplicationAgent failed for %s: %s",
                                   paper.get("paper_id", "?"), e)

        await asyncio.gather(*[_analyze_one(p) for p in papers])
        logger.info("ReplicationAgent: analyzed %d/%d papers", len(results), len(papers))
        return results

    async def analyze(self, paper: Dict) -> ReplicationProblem:
        title = paper.get("metadata", {}).get("title", paper.get("title", ""))
        year = paper.get("metadata", {}).get("year", paper.get("year", 0))
        paper_id = paper.get("paper_id", "")

        content = paper.get("full_text", "") or paper.get("abstract", "") or \
            paper.get("metadata", {}).get("abstract", "")
        if not content or len(content) < 30:
            return None

        prompt = _PROMPT.format(year=year, title=title, content=content[:4000])
        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        issues = data.get("reproduction_issues", [])
        issue_descriptions = [i.get("issue", "") if isinstance(i, dict) else str(i)
                              for i in issues]

        improvements = data.get("potential_improvements", [])
        first_improvement = improvements[0] if improvements else ""

        experiments = data.get("suggested_experiments", [])
        first_experiment = experiments[0] if experiments else ""

        return ReplicationProblem(
            paper_id=paper_id,
            paper_title=title,
            claimed_result=data.get("claimed_result", ""),
            reproduction_issue="; ".join(issue_descriptions),
            missing_details=data.get("missing_details", []),
            suggested_experiment=first_experiment,
            potential_improvement=first_improvement,
        )
