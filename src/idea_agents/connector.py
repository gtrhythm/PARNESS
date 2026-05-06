import logging
import random
from typing import List

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, IdeaSeed, CrossDomainPair, ResearchDirection

logger = logging.getLogger(__name__)

_PROMPT = """You are a creative researcher who finds non-obvious connections between seemingly unrelated work.

Given two paper insights from DIFFERENT research areas, find:
1. A structural analogy (what's similar in how they approach their problem)
2. A transferable idea (what technique/insight from A could apply to B's domain, or vice versa)

## Insight A: [{year_a}] {title_a}
  Core: {insight_a}
  Key trick: {trick_a}
  Limitations: {lim_a}

## Insight B: [{year_b}] {title_b}
  Core: {insight_b}
  Key trick: {trick_b}
  Limitations: {lim_b}

Return JSON:
{{
  "structural_analogy": "what's structurally similar despite surface differences",
  "transfer_direction": "A→B or B→A",
  "surface_similarity": 0.2,
  "idea_seed": {{
    "seed": "one-line novel research idea from this cross-domain transfer",
    "rationale": "why this transfer is novel and feasible",
    "novelty_signal": "what makes this non-obvious"
  }}
}}

If these two insights are genuinely too similar or too disconnected to produce a meaningful idea,
set idea_seed to null.
{direction_text}
"""


class ConnectorAgent:
    def __init__(self, llm_client, max_pairs: int = 10, budget=None):
        self.llm = llm_client
        self.max_pairs = max_pairs
        self.budget = budget

    async def connect(self, insights: List[CompressedInsight], direction: ResearchDirection = None) -> dict:
        pairs = self._select_diverse_pairs(insights, direction)
        direction_text = ""
        if direction:
            direction_text = f"\n{direction.prompt_block()}\nFocus your analysis on this specific research direction.\n"
        connector_seeds = []
        cross_domain_pairs = []

        for i, j in pairs:
            try:
                result = await self._connect_pair(insights[i], insights[j], direction_text)
                if result and result.get("idea_seed"):
                    seed_data = result["idea_seed"]
                    seed = IdeaSeed(
                        seed=seed_data.get("seed", ""),
                        seed_type="cross_domain",
                        source_papers=[insights[i].paper_id, insights[j].paper_id],
                        rationale=seed_data.get("rationale", ""),
                        novelty_signal=seed_data.get("novelty_signal", ""),
                        related_insights=[insights[i].core_insight, insights[j].core_insight],
                    )
                    connector_seeds.append(seed)

                    cross_domain_pairs.append(CrossDomainPair(
                        insight_a_idx=i,
                        insight_b_idx=j,
                        surface_similarity=result.get("surface_similarity", 0.3),
                        structural_analogy=result.get("structural_analogy", ""),
                        transfer_direction=result.get("transfer_direction", ""),
                        idea_seed=seed,
                    ))
            except Exception as e:
                logger.warning("Connector failed for pair (%d, %d): %s", i, j, e)

        logger.info("Connector: %d cross-domain seeds from %d pairs", len(connector_seeds), len(pairs))
        return {"seeds": connector_seeds, "pairs": cross_domain_pairs}

    def _select_diverse_pairs(self, insights: List[CompressedInsight], direction: ResearchDirection = None) -> List[tuple]:
        n = len(insights)
        if n < 2:
            return []

        all_pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                kw_i = set(str(insights[i].key_trick).lower().split())
                kw_j = set(str(insights[j].key_trick).lower().split())
                overlap = len(kw_i & kw_j) / max(len(kw_i | kw_j), 1)
                if 0.0 < overlap < 0.5:
                    all_pairs.append((i, j, overlap))

        all_pairs.sort(key=lambda x: x[2])
        diverse = all_pairs[:self.max_pairs]

        if len(diverse) < 3 and len(all_pairs) > len(diverse):
            diverse = all_pairs[:self.max_pairs]

        if direction and direction.keywords:
            direction_kws = set(k.lower() for k in direction.keywords)
            def _dir_relevance(pair):
                i, j, _ = pair
                text_i = f"{insights[i].key_trick} {insights[i].core_insight}".lower()
                text_j = f"{insights[j].key_trick} {insights[j].core_insight}".lower()
                match = any(kw in text_i or kw in text_j for kw in direction_kws)
                return 0 if match else 1
            diverse.sort(key=lambda x: (_dir_relevance(x), x[2]))

        return [(i, j) for i, j, _ in diverse]

    async def _connect_pair(self, a: CompressedInsight, b: CompressedInsight, direction_text: str = "") -> dict:
        prompt = _PROMPT.format(
            year_a=a.year, title_a=a.title,
            insight_a=a.core_insight, trick_a=a.key_trick,
            lim_a="; ".join(a.limitations[:2]),
            year_b=b.year, title_b=b.title,
            insight_b=b.core_insight, trick_b=b.key_trick,
            lim_b="; ".join(b.limitations[:2]),
            direction_text=direction_text,
        )
        resp = await call_llm(self.llm, prompt)
        return parse_json_response(resp)
