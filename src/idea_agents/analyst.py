import logging
from typing import List

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, IdeaSeed, SeedCluster, ResearchDirection

logger = logging.getLogger(__name__)

_PROMPT = """You are a research analyst examining a collection of paper insights. Your job is to:
1. Group insights into 3-6 thematic clusters
2. For each cluster, identify shared limitations
3. Find gaps between clusters (unexplored intersections)
4. Find intra-cluster gaps (repeated limitations that no paper addresses)

## Paper Insights:
{insights_text}

Return JSON:
{{
  "clusters": [
    {{
      "theme": "cluster theme name",
      "paper_indices": [0, 3, 5],
      "shared_limitations": ["limitation shared by multiple papers"],
      "gaps": [
        {{
          "seed": "one-line research idea that addresses this gap",
          "rationale": "why this gap exists and why it matters",
          "type": "intra_cluster"
        }}
      ]
    }}
  ],
  "cross_cluster_gaps": [
    {{
      "seed": "one-line idea bridging two clusters",
      "cluster_pair": ["cluster A theme", "cluster B theme"],
      "rationale": "why combining these is novel",
      "type": "cross_cluster"
    }}
  ]
}}

Rules:
- Focus on actionable gaps, not vague "future work"
- Each gap should be specific enough to be a research project
- Cross-cluster gaps are the most valuable — they represent unexplored territory
"""

_MAX_INSIGHTS_PER_CALL = 200


class AnalystAgent:
    def __init__(self, llm_client, budget=None):
        self.llm = llm_client
        self.budget = budget

    def _input_budget(self, fraction: float) -> int:
        if self.budget:
            return int(self.budget.max_context * fraction)
        return int(128000 * fraction)

    async def analyze(self, insights: List[CompressedInsight], direction: ResearchDirection = None) -> dict:
        if len(insights) <= _MAX_INSIGHTS_PER_CALL:
            return await self._analyze_batch(insights, direction)

        all_clusters = []
        all_seeds = []
        for i in range(0, len(insights), _MAX_INSIGHTS_PER_CALL):
            batch = insights[i:i + _MAX_INSIGHTS_PER_CALL]
            logger.info("Analyst batch %d: %d insights", i // _MAX_INSIGHTS_PER_CALL + 1, len(batch))
            try:
                result = await self._analyze_batch(batch, direction)
                all_clusters.extend(result["clusters"])
                all_seeds.extend(result["seeds"])
            except Exception as e:
                logger.warning("Analyst batch failed: %s", e)

        if len(all_clusters) > 6:
            try:
                merged = await self._merge_clusters(all_clusters, all_seeds)
                all_clusters = merged["clusters"]
                all_seeds = merged["seeds"]
            except Exception as e:
                logger.warning("Cluster merge failed: %s", e)

        logger.info("Analyst: %d clusters, %d seeds (from %d insights in %d batches)",
                     len(all_clusters), len(all_seeds), len(insights),
                     (len(insights) + _MAX_INSIGHTS_PER_CALL - 1) // _MAX_INSIGHTS_PER_CALL)
        return {"clusters": all_clusters, "seeds": all_seeds}

    async def _analyze_batch(self, insights: List[CompressedInsight], direction: ResearchDirection = None) -> dict:
        insights_text = ""
        for i, ins in enumerate(insights):
            insights_text += f"\n[{i}] ({ins.year}) {ins.title}\n"
            insights_text += f"  Insight: {ins.core_insight}\n"
            insights_text += f"  Key trick: {ins.key_trick}\n"
            insights_text += f"  Limitations: {'; '.join(ins.limitations[:3])}\n"
            insights_text += f"  Open Qs: {'; '.join(ins.open_questions[:2])}\n"

        direction_text = ""
        if direction:
            direction_text = f"\n{direction.prompt_block()}\nFocus your analysis on this specific research direction.\n"
            insights_text += direction_text

        prompt = _PROMPT.format(insights_text=insights_text)
        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        clusters = []
        analyst_seeds = []

        for c in data.get("clusters", []):
            cluster = SeedCluster(
                theme=c.get("theme", ""),
                insight_indices=c.get("paper_indices", []),
                common_limitations=c.get("shared_limitations", []),
            )
            for g in c.get("gaps", []):
                seed = IdeaSeed(
                    seed=g.get("seed", ""),
                    seed_type="intra_cluster",
                    rationale=g.get("rationale", ""),
                    novelty_signal="addresses_repeated_limitation",
                )
                cluster.gaps.append(seed)
                analyst_seeds.append(seed)
            clusters.append(cluster)

        for g in data.get("cross_cluster_gaps", []):
            seed = IdeaSeed(
                seed=g.get("seed", ""),
                seed_type="cross_cluster",
                rationale=g.get("rationale", ""),
                novelty_signal=f"bridges: {g.get('cluster_pair', [])}",
            )
            analyst_seeds.append(seed)

        return {"clusters": clusters, "seeds": analyst_seeds}

    async def _merge_clusters(self, clusters: list, seeds: list) -> dict:
        themes_text = ""
        for i, c in enumerate(clusters):
            if isinstance(c, SeedCluster):
                theme = c.theme
                lims = "; ".join(c.common_limitations[:3])
            else:
                theme = c.get("theme", "")
                lims = "; ".join(c.get("common_limitations", [])[:3])
            themes_text += f"\n[{i}] {theme} — Limitations: {lims}"

        prompt = f"""Merge these {len(clusters)} cluster themes into 3-6 final clusters.
{themes_text}

Return JSON:
{{
  "merged_clusters": [
    {{"theme": "...", "source_indices": [0, 2, 4], "shared_limitations": ["..."]}}
  ],
  "new_cross_gaps": [
    {{"seed": "...", "rationale": "...", "type": "cross_cluster"}}
  ]
}}
"""
        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        merged_clusters = []
        for mc in data.get("merged_clusters", []):
            merged_clusters.append(SeedCluster(
                theme=mc.get("theme", ""),
                insight_indices=mc.get("source_indices", []),
                common_limitations=mc.get("shared_limitations", []),
            ))

        new_seeds = []
        for g in data.get("new_cross_gaps", []):
            new_seeds.append(IdeaSeed(
                seed=g.get("seed", ""),
                seed_type="cross_cluster",
                rationale=g.get("rationale", ""),
                novelty_signal="merged_gap",
            ))

        return {"clusters": merged_clusters, "seeds": seeds + new_seeds}
