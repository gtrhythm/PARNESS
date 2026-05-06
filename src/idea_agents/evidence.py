import asyncio
import logging
from typing import Dict, List

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, Hypothesis, EvidenceItem

logger = logging.getLogger(__name__)

_PROMPT = """You are a researcher collecting evidence for or against specific hypotheses.

Hypothesis: {hypothesis_statement}

Papers to search for evidence:
{papers_text}

For each piece of evidence found, return JSON:
{{
  "evidence_items": [
    {{
      "paper_title": "Title of the paper providing evidence",
      "stance": "supporting|refuting|mixed|neutral",
      "evidence_description": "What specific finding/method/result is relevant",
      "strength": "strong|moderate|weak",
      "relevance": 0.0-1.0
    }}
  ],
  "overall_assessment": "brief summary of evidence balance"
}}

Rules:
- Each evidence item must reference a SPECIFIC finding from a paper
- Stance: supporting (backs the hypothesis), refuting (contradicts it), mixed (both), neutral (related but inconclusive)
- Strength: strong (direct evidence), moderate (indirect), weak (tangential)
- Relevance: how directly this evidence speaks to the hypothesis
- Be honest about the evidence; do not cherry-pick
"""


class EvidenceAgent:
    def __init__(self, llm_client, max_concurrent: int = 4):
        self.llm = llm_client
        self.max_concurrent = max_concurrent

    async def collect_evidence(
        self,
        hypotheses: List[Hypothesis],
        insights: List[CompressedInsight],
    ) -> List[EvidenceItem]:
        if not hypotheses or not insights:
            return []

        papers_text = "\n".join(
            f"- [{ins.year}] {ins.title}: {ins.core_insight}\n"
            f"  key_trick: {ins.key_trick}\n"
            f"  limitations: {'; '.join(ins.limitations[:2])}"
            for ins in insights
        )

        sem = asyncio.Semaphore(self.max_concurrent)
        all_evidence = []

        async def _collect_one(hypothesis: Hypothesis):
            async with sem:
                try:
                    evidence = await self._collect_for_hypothesis(
                        hypothesis, papers_text
                    )
                    all_evidence.extend(evidence)
                except Exception as e:
                    logger.warning("EvidenceAgent failed for hypothesis %s: %s",
                                   hypothesis.hypothesis_id, e)

        await asyncio.gather(*[_collect_one(h) for h in hypotheses])
        logger.info("EvidenceAgent: collected %d evidence items for %d hypotheses",
                     len(all_evidence), len(hypotheses))
        return all_evidence

    async def _collect_for_hypothesis(
        self,
        hypothesis: Hypothesis,
        papers_text: str,
    ) -> List[EvidenceItem]:
        prompt = _PROMPT.format(
            hypothesis_statement=hypothesis.statement,
            papers_text=papers_text[:5000],
        )
        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        return [
            EvidenceItem(
                hypothesis_id=hypothesis.hypothesis_id,
                paper_id="",
                paper_title=e.get("paper_title", ""),
                stance=e.get("stance", "neutral"),
                evidence_description=e.get("evidence_description", ""),
                strength=e.get("strength", "weak"),
                relevance=e.get("relevance", 0.0),
            )
            for e in data.get("evidence_items", [])
        ]
