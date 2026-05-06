import asyncio
import logging
from typing import Dict, List

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, Hypothesis

logger = logging.getLogger(__name__)

_PROMPT = """You are a researcher generating testable hypotheses from literature analysis.

Research context:
{context}

Insights from papers:
{insights_text}

Generate specific, testable research hypotheses. Return JSON:
{{
  "hypotheses": [
    {{
      "statement": "A clear, testable hypothesis statement",
      "rationale": "Why this hypothesis makes sense based on the evidence",
      "testability": "How this could be tested experimentally",
      "source_papers": ["papers that support this hypothesis"],
      "predicted_outcome": "What you expect to find if the hypothesis is correct",
      "required_experiment": "Brief description of the experiment needed",
      "confidence": 0.0-1.0
    }}
  ]
}}

Rules:
- Hypotheses must be FALSIFIABLE - there must be a way to disprove them
- Each hypothesis should connect insights from at least one paper
- Confidence should reflect how strongly the evidence supports the hypothesis
- The required experiment should be practically achievable
- Avoid vague hypotheses; be specific about relationships, effects, and mechanisms
"""


class HypothesisAgent:
    def __init__(self, llm_client):
        self.llm = llm_client

    async def generate(
        self,
        insights: List[CompressedInsight],
        context: str = "",
        max_hypotheses: int = 10,
    ) -> List[Hypothesis]:
        if not insights:
            return []

        insights_text = "\n".join(
            f"- [{ins.year}] {ins.title}: {ins.core_insight}\n"
            f"  problem: {ins.problem_solved}\n"
            f"  open_questions: {'; '.join(ins.open_questions[:2])}"
            for ins in insights
        )

        prompt = _PROMPT.format(
            context=context or "General research exploration",
            insights_text=insights_text[:5000],
        )
        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        hypotheses = []
        for h in data.get("hypotheses", [])[:max_hypotheses]:
            import hashlib
            stmt = h.get("statement", "")
            hid = hashlib.sha256(stmt.lower().encode()).hexdigest()[:12]
            hypotheses.append(Hypothesis(
                hypothesis_id=hid,
                statement=stmt,
                rationale=h.get("rationale", ""),
                testability=h.get("testability", ""),
                source_papers=h.get("source_papers", []),
                predicted_outcome=h.get("predicted_outcome", ""),
                required_experiment=h.get("required_experiment", ""),
                confidence=h.get("confidence", 0.0),
            ))

        logger.info("HypothesisAgent: generated %d hypotheses", len(hypotheses))
        return hypotheses
