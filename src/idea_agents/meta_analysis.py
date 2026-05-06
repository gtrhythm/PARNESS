import asyncio
import logging
from typing import Dict, List

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, GapItem, TrendItem

logger = logging.getLogger(__name__)

_PROMPT = """You are a meta-researcher analyzing a collection of papers to discover trends and gaps.

Papers summary:
{papers_summary}

Perform a meta-analysis. Return JSON:
{{
  "trends": [
    {{
      "trend_name": "Name of the trend",
      "description": "What this trend is about",
      "supporting_papers": ["titles of papers supporting this trend"],
      "growth_rate": "increasing|stable|decreasing",
      "related_gaps": ["gaps related to this trend"]
    }}
  ],
  "gaps": [
    {{
      "gap_description": "Description of the research gap",
      "domain": "Which sub-domain this gap is in",
      "evidence_papers": ["papers that reveal or relate to this gap"],
      "opportunity_score": 0.0-1.0
    }}
  ]
}}

Rules:
- Identify macro-level trends across papers, not individual paper contributions
- Gaps should be about missing research, not just paper limitations
- Opportunity score reflects both importance and feasibility of filling the gap
- Look for patterns: what topics are rising, what methods are converging, what's being neglected
"""


class MetaAnalysisAgent:
    def __init__(self, llm_client):
        self.llm = llm_client

    async def analyze(
        self,
        insights: List[CompressedInsight],
    ) -> Dict:
        if not insights:
            return {"trends": [], "gaps": []}

        papers_summary = "\n".join(
            f"- [{ins.year}] {ins.title}: {ins.core_insight}\n"
            f"  problem: {ins.problem_solved}\n"
            f"  limitations: {'; '.join(ins.limitations[:3])}\n"
            f"  open_questions: {'; '.join(ins.open_questions[:3])}"
            for ins in insights
        )

        prompt = _PROMPT.format(papers_summary=papers_summary[:6000])
        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        trends = [
            TrendItem(
                trend_name=t.get("trend_name", ""),
                description=t.get("description", ""),
                supporting_papers=t.get("supporting_papers", []),
                growth_rate=t.get("growth_rate", ""),
                related_gaps=t.get("related_gaps", []),
            )
            for t in data.get("trends", [])
        ]

        gaps = [
            GapItem(
                gap_description=g.get("gap_description", ""),
                domain=g.get("domain", ""),
                evidence_papers=g.get("evidence_papers", []),
                opportunity_score=g.get("opportunity_score", 0.0),
            )
            for g in data.get("gaps", [])
        ]

        logger.info("MetaAnalysisAgent: found %d trends, %d gaps",
                     len(trends), len(gaps))
        return {"trends": trends, "gaps": gaps}
