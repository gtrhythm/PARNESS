import logging
from typing import List, Optional

from .llm_utils import call_llm, parse_json_response
from .merger import HierarchicalMerger, FocusedRetriever, _format_idea
from .models import IdeaSeed, CompressedInsight, FullIdea, ResearchDirection, LiteratureSurvey
from .token_budget import PromptBudget

logger = logging.getLogger(__name__)

_SEED_PROMPT = """You are a research synthesizer. Expand idea seeds into full research proposals.

## Available paper insights (for grounding):
{insights_text}

## Idea seeds to expand:
{seeds_text}

For each seed, produce a FULL research proposal. Return JSON:
{{
  "ideas": [
    {{
      "title": "concise research title",
      "description": "300-500 word detailed proposal covering: problem statement, proposed approach, key technical contribution, expected experiments",
      "category": "one of: architecture, loss_function, training_technique, data_processing, task_formulation, combination, application",
      "methodology": "specific technical approach with enough detail to be actionable",
      "expected_results": "anticipated experimental outcomes and metrics",
      "required_resources": "compute/data requirements",
      "risk_analysis": "main risks and mitigation strategies",
      "source_papers": ["paper_ids referenced"],
      "seed_type": "gap|cross_domain|contrarian",
      "rationale": "why this idea is novel and worth pursuing"
    }}
  ]
}}

Rules:
- Each idea must be SPECIFIC enough to start coding within a week
- Methodology should name concrete techniques, not just "we will use deep learning"
- Source papers should reference actual paper_ids from the insights
- Target: {target_count} ideas
"""


class SynthesizerAgent:
    def __init__(self, llm_client, budget: PromptBudget = None):
        self.llm = llm_client
        self.budget = budget or PromptBudget(max_context=128000)
        self.merger = HierarchicalMerger(llm_client)
        self.retriever = FocusedRetriever()

    async def synthesize(
        self,
        seeds: List[IdeaSeed],
        insights: List[CompressedInsight],
        target_count: int = 20,
        existing_ideas: List[dict] = None,
        retrieval_mode: str = "all",
        retrieval_query: str = "",
        direction: ResearchDirection = None,
        literature_survey: LiteratureSurvey = None,
    ) -> List[FullIdea]:
        if len(seeds) > 20:
            return await self._batched_synthesize(
                seeds, insights, target_count, existing_ideas, retrieval_mode, retrieval_query, direction, literature_survey,
            )

        insights_text = ""
        for ins in insights[:40]:
            insights_text += f"- [{ins.paper_id}] {ins.core_insight}\n"
            if ins.key_trick:
                insights_text += f"  Trick: {ins.key_trick}\n"

        seeds_text = ""
        for i, seed in enumerate(seeds):
            seeds_text += f"\n[{i}] [{seed.seed_type}] {seed.seed}"
            seeds_text += f"\n    Rationale: {seed.rationale[:200]}"

        direction_text = ""
        if direction:
            direction_text = f"\n{direction.prompt_block()}\nFocus your synthesis on this specific research direction.\n"
        if literature_survey and literature_survey.summary:
            direction_text += f"\n## Literature Survey: {literature_survey.direction}\n{literature_survey.summary}\n"

        full_input = insights_text + direction_text + seeds_text
        max_ideas = self.budget.max_ideas_per_request(full_input)
        effective_target = min(target_count, max_ideas)

        prompt = _SEED_PROMPT.format(
            insights_text=(insights_text[:self.budget.truncate_to_budget(
                insights, lambda i: f"- [{i.paper_id}] {i.core_insight}\n",
                int(self.budget.max_context * 0.2),
            )] + direction_text),
            seeds_text=seeds_text[:self.budget.truncate_to_budget(
                seeds, lambda s: f"[0] [{s.seed_type}] {s.seed}\n",
                int(self.budget.max_context * 0.15),
            )],
            target_count=effective_target,
        )

        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        new_ideas = []
        for item in data.get("ideas", []):
            new_ideas.append(FullIdea(
                title=item.get("title", ""),
                description=item.get("description", ""),
                category=item.get("category", ""),
                methodology=item.get("methodology", ""),
                expected_results=item.get("expected_results", ""),
                required_resources=item.get("required_resources", ""),
                risk_analysis=item.get("risk_analysis", ""),
                source_papers=item.get("source_papers", []),
                seed_type=item.get("seed_type", ""),
                rationale=item.get("rationale", ""),
            ))

        if existing_ideas:
            merged = await self._merge_with_existing(new_ideas, existing_ideas, target_count, retrieval_mode, retrieval_query)
            return merged

        logger.info("Synthesizer: expanded %d seeds into %d full ideas", len(seeds), len(new_ideas))
        return new_ideas

    async def _batched_synthesize(
        self,
        seeds: List[IdeaSeed],
        insights: List[CompressedInsight],
        target_count: int,
        existing_ideas: List[dict],
        retrieval_mode: str,
        retrieval_query: str,
        direction: ResearchDirection = None,
        literature_survey: LiteratureSurvey = None,
    ) -> List[FullIdea]:
        batch_size = 15
        batches = self.budget.plan_batches(seeds, insights, target_count, batch_size)
        all_ideas = []

        for batch_info in batches:
            batch = batch_info["seeds"]
            per_batch = batch_info["ideas_per_batch"]
            logger.info("Synthesizer batch %d: %d seeds → %d ideas (context-aware)",
                        batch_info["seed_start"] // batch_size + 1, len(batch), per_batch)
            try:
                ideas = await self._synthesize_batch(batch, insights[:30], per_batch, direction, literature_survey)
                all_ideas.extend(ideas)
            except Exception as e:
                logger.warning("Synthesizer batch %d failed: %s", batch_info["seed_start"] // batch_size + 1, e)

        if existing_ideas:
            merged = await self._merge_with_existing(all_ideas, existing_ideas, target_count, retrieval_mode, retrieval_query)
            return merged

        return all_ideas[:target_count]

    async def _synthesize_batch(
        self,
        seeds: List[IdeaSeed],
        insights: List[CompressedInsight],
        target_count: int,
        direction: ResearchDirection = None,
        literature_survey: LiteratureSurvey = None,
    ) -> List[FullIdea]:
        insights_text = ""
        for ins in insights:
            insights_text += f"- [{ins.paper_id}] {ins.core_insight}\n"

        seeds_text = ""
        for i, seed in enumerate(seeds):
            seeds_text += f"\n[{i}] [{seed.seed_type}] {seed.seed}"
            seeds_text += f"\n    Rationale: {seed.rationale[:150]}"

        direction_text = ""
        if direction:
            direction_text = f"\n{direction.prompt_block()}\nFocus your synthesis on this specific research direction.\n"
        if literature_survey and literature_survey.summary:
            direction_text += f"\n## Literature Survey: {literature_survey.direction}\n{literature_survey.summary}\n"

        full_input = insights_text + direction_text + seeds_text
        max_ideas = self.budget.max_ideas_per_request(full_input)
        effective_target = min(target_count, max_ideas)

        input_budget = int(self.budget.max_context * 0.2)
        seed_budget = int(self.budget.max_context * 0.15)

        prompt = _SEED_PROMPT.format(
            insights_text=(insights_text[:input_budget] + direction_text),
            seeds_text=seeds_text[:seed_budget],
            target_count=effective_target,
        )

        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        ideas = []
        for item in data.get("ideas", []):
            ideas.append(FullIdea(
                title=item.get("title", ""),
                description=item.get("description", ""),
                category=item.get("category", ""),
                methodology=item.get("methodology", ""),
                expected_results=item.get("expected_results", ""),
                required_resources=item.get("required_resources", ""),
                risk_analysis=item.get("risk_analysis", ""),
                source_papers=item.get("source_papers", []),
                seed_type=item.get("seed_type", ""),
                rationale=item.get("rationale", ""),
            ))
        return ideas

    async def _merge_with_existing(
        self,
        new_ideas: List[FullIdea],
        existing_ideas: List[dict],
        target_count: int,
        retrieval_mode: str,
        retrieval_query: str,
    ) -> List[FullIdea]:
        all_dicts = [i.to_dict() for i in new_ideas] + existing_ideas

        referenced = self.retriever.retrieve(
            all_dicts,
            mode=retrieval_mode,
            query=retrieval_query,
            top_k=100,
        )

        total_tokens = sum(
            len(_format_idea(i)) for i in referenced
        )

        if total_tokens > 20000:
            logger.info("Synthesizer: %d ideas exceed context, using hierarchical merge", len(referenced))
            merged = await self.merger.merge(referenced, target_count=target_count)
            ideas = []
            for d in merged:
                if isinstance(d, FullIdea):
                    ideas.append(d)
                else:
                    ideas.append(FullIdea(
                        title=d.get("title", ""),
                        description=d.get("description", ""),
                        category=d.get("category", ""),
                        methodology=d.get("methodology", ""),
                        seed_type=d.get("seed_type", "merged"),
                        rationale=d.get("rationale", ""),
                    ))
            return ideas

        logger.info("Synthesizer: %d new + %d existing, within context budget", len(new_ideas), len(existing_ideas))
        return new_ideas
