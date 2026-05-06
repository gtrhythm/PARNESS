import logging
from typing import List

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, IdeaSeed, ResearchDirection

logger = logging.getLogger(__name__)

_PROMPT = """You are a contrarian researcher who challenges prevailing assumptions.

Given these assumptions that papers make but don't prove, generate research ideas by REVERSING them.

## Paper Assumptions:
{assumptions_text}

## Paper Insights (for context):
{insights_text}

Generate 5-8 contrarian research ideas. For each:
- Identify which assumption you're challenging
- Propose what happens when that assumption is WRONG
- Suggest a concrete research direction

Return JSON:
{{
  "contrarian_seeds": [
    {{
      "seed": "one-line research idea",
      "challenged_assumption": "the assumption being reversed",
      "flipped_to": "what if instead...",
      "rationale": "why this is worth exploring",
      "source_papers": ["paper_id"]
    }}
  ]
}}
"""


class ContrarianAgent:
    def __init__(self, llm_client, budget=None):
        self.llm = llm_client
        self.budget = budget

    def _input_budget(self, fraction: float) -> int:
        if self.budget:
            return int(self.budget.max_context * fraction)
        return int(128000 * fraction)

    async def challenge(self, insights: List[CompressedInsight], direction: ResearchDirection = None) -> dict:
        assumptions_text = ""
        insights_text = ""
        for i, ins in enumerate(insights):
            if ins.assumed_but_not_proven:
                for a in ins.assumed_but_not_proven:
                    assumptions_text += f"- [{ins.paper_id}] {a}\n"
            insights_text += f"- [{ins.paper_id}] {ins.core_insight}\n"

        if not assumptions_text.strip():
            assumptions_text = "(No explicit unproven assumptions found. Infer implicit assumptions from the insights above.)"

        direction_text = ""
        if direction:
            direction_text = f"\n{direction.prompt_block()}\nFocus your contrarian analysis on assumptions related to this specific research direction.\n"

        prompt = _PROMPT.format(
            assumptions_text=assumptions_text[:self._input_budget(0.2)],
            insights_text=insights_text[:self._input_budget(0.15)] + direction_text,
        )
        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        seeds = []
        for s in data.get("contrarian_seeds", []):
            seeds.append(IdeaSeed(
                seed=s.get("seed", ""),
                seed_type="contrarian",
                source_papers=s.get("source_papers", []),
                rationale=s.get("rationale", ""),
                novelty_signal=f"challenges: {s.get('challenged_assumption', '')}",
                related_insights=[s.get("challenged_assumption", ""), s.get("flipped_to", "")],
            ))

        logger.info("Contrarian: %d seeds from %d assumptions", len(seeds), len(insights))
        return {"seeds": seeds}
