import logging
from typing import List

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, FullIdea, ResearchDirection

logger = logging.getLogger(__name__)

_PROMPT = """You are a senior ICLR Area Chair reviewing research ideas. Be STRICT.

## Original paper insights (ground truth for novelty check):
{insights_text}

## Ideas to evaluate:
{ideas_text}

For each idea, evaluate against the papers above. Check:
1. Has this already been done by one of these papers?
2. Is this just a trivial combination?
3. Does the methodology make sense?

Return JSON:
{{
  "evaluations": [
    {{
      "idea_title": "...",
      "novelty_score": 7.5,
      "feasibility_score": 8.0,
      "impact_score": 7.0,
      "overall_score": 7.5,
      "direction_alignment_score": 8.0,
      "already_done_by": null,
      "strengths": ["..."],
      "weaknesses": ["..."],
      "recommendation": "accept|weak_accept|borderline|reject"
    }}
  ]
}}

Scoring: 1-10, where 7+ = strong, 5-7 = borderline, <5 = weak.
Be harsh on ideas that don't clearly differentiate from the source papers.
{direction_text}
"""


class CriticAgent:
    def __init__(self, llm_client, budget=None):
        self.llm = llm_client
        self.budget = budget

    def _input_budget(self, fraction: float) -> int:
        if self.budget:
            return int(self.budget.max_context * fraction)
        return int(128000 * fraction)

    async def critique(
        self,
        ideas: List[FullIdea],
        insights: List[CompressedInsight],
        target_count: int = 20,
        direction: ResearchDirection = None,
    ) -> List[FullIdea]:
        batch_size = 10
        all_evaluated = []

        for i in range(0, len(ideas), batch_size):
            batch = ideas[i:i + batch_size]
            try:
                evaluated = await self._evaluate_batch(batch, insights, direction)
                all_evaluated.extend(evaluated)
            except Exception as e:
                logger.warning("Critic batch %d failed: %s", i, e)
                all_evaluated.extend(batch)

        all_evaluated.sort(key=lambda x: x.overall_score, reverse=True)
        result = all_evaluated[:target_count]

        logger.info("Critic: %d → %d ideas (avg score: %.1f)",
                     len(ideas), len(result),
                     sum(i.overall_score for i in result) / max(len(result), 1))
        return result

    async def _evaluate_batch(
        self,
        ideas: List[FullIdea],
        insights: List[CompressedInsight],
        direction: ResearchDirection = None,
    ) -> List[FullIdea]:
        insights_text = "\n".join(
            f"- [{ins.paper_id}] {ins.core_insight}" for ins in insights[:20]
        )
        ideas_text = ""
        for j, idea in enumerate(ideas):
            ideas_text += f"\n### Idea {j + 1}: {idea.title}\n"
            ideas_text += f"Category: {idea.category}\n"
            ideas_text += f"Seed type: {idea.seed_type}\n"
            ideas_text += f"Description: {idea.description[:400]}\n"
            ideas_text += f"Methodology: {idea.methodology[:200]}\n"

        direction_text = ""
        if direction:
            direction_text = f"\n{direction.prompt_block()}\nEvaluate how well each idea aligns with this research direction using the direction_alignment_score field.\n"

        prompt = _PROMPT.format(
            insights_text=insights_text[:self._input_budget(0.15)],
            ideas_text=ideas_text[:self._input_budget(0.3)],
            direction_text=direction_text if direction else "",
        )

        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        evals = {e.get("idea_title", ""): e for e in data.get("evaluations", [])}

        evaluated = []
        for idea in ideas:
            ev = evals.get(idea.title, {})
            if ev:
                idea.novelty_score = float(ev.get("novelty_score", 5.0))
                idea.feasibility_score = float(ev.get("feasibility_score", 5.0))
                idea.impact_score = float(ev.get("impact_score", 5.0))
                idea.overall_score = float(ev.get("overall_score",
                    (idea.novelty_score + idea.feasibility_score + idea.impact_score) / 3))
                idea.strengths = ev.get("strengths", [])
                idea.weaknesses = ev.get("weaknesses", [])
                if "direction_alignment_score" in ev:
                    idea.direction_alignment_score = float(ev["direction_alignment_score"])
            evaluated.append(idea)

        return evaluated
