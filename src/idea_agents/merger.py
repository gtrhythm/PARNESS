import logging
from typing import Callable, Dict, List, Optional

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight
from .store import ContextBudget, IdeaGroup

logger = logging.getLogger(__name__)

_GROUP_SYNTH_PROMPT = """You are a senior researcher. Below is a group of {count} existing research ideas from previous brainstorming sessions.

## Ideas in this group (theme: {theme}):
{ideas_text}

Synthesize these ideas into a SINGLE concise summary that captures:
1. The key themes and directions covered
2. Common patterns or contradictions across these ideas  
3. One or two NEW angles that emerge from viewing them together

Return JSON:
{{
  "theme": "identified theme for this group",
  "synthesis": "2-3 sentence synthesis capturing the essence and opening new angles",
  "emergent_angles": ["new angle 1", "new angle 2"]
}}

Keep synthesis under 200 words. Focus on what's MISSING, not just what's there.
"""

_MERGE_PROMPT = """You are a research director reviewing {count} group syntheses from your team's brainstorming.

## Group Syntheses:
{groups_text}

Your task: produce {target_count} NEW research ideas by combining insights across these groups.

Rules:
- Ideas must be DIFFERENT from what's described in the syntheses (build on gaps, not repeat)
- Cross-pollinate between groups (take an angle from group A and apply it to group B's domain)
- Each idea should reference which groups it draws from

Return JSON:
{{
  "ideas": [
    {{
      "title": "...",
      "description": "300-500 word proposal",
      "category": "architecture|training_technique|loss_function|data_processing|task_formulation|combination|application",
      "methodology": "specific technical approach",
      "source_groups": [1, 3],
      "seed_type": "merged",
      "rationale": "why this cross-group idea is novel"
    }}
  ]
}}
"""


def _format_idea(idea: Dict) -> str:
    return (
        f"- [{idea.get('seed_type', '?')}] {idea.get('title', '')}\n"
        f"  Category: {idea.get('category', '')}\n"
        f"  {idea.get('description', '')[:250]}"
    )


def _format_group(group: IdeaGroup, idx: int) -> str:
    return (
        f"### Group {idx + 1}: {group.theme} ({len(group.ideas)} ideas)\n"
        f"{group.synthesis}\n"
    )


class HierarchicalMerger:
    def __init__(self, llm_client, budget: ContextBudget = None):
        self.llm = llm_client
        self.budget = budget or ContextBudget()

    async def merge(
        self,
        all_ideas: List[Dict],
        target_count: int = 20,
        max_tokens_per_chunk: int = 5000,
    ) -> List[Dict]:
        if not all_ideas:
            return []

        if self.budget.estimate_tokens(
            "\n".join(_format_idea(i) for i in all_ideas)
        ) <= max_tokens_per_chunk:
            return all_ideas

        chunks = self.budget.chunk_by_budget(all_ideas, _format_idea, max_tokens_per_chunk)
        logger.info("HierarchicalMerger: %d ideas → %d groups", len(all_ideas), len(chunks))

        groups = []
        for i, chunk in enumerate(chunks):
            try:
                group = await self._synthesize_group(chunk, i)
                groups.append(group)
            except Exception as e:
                logger.warning("Group synthesis %d failed: %s", i, e)
                groups.append(IdeaGroup(
                    group_id=f"group_{i}",
                    ideas=chunk,
                    theme=f"fallback_group_{i}",
                    synthesis="; ".join(idea.get("title", "") for idea in chunk[:5]),
                ))

        level = 0
        while len(groups) > 1:
            level += 1
            groups = await self._merge_groups(groups, level)
            logger.info("Merge level %d: %d groups remaining", level, len(groups))

        if len(groups) == 1 and groups[0].synthesis:
            merged_ideas = await self._generate_from_synthesis(groups[0], target_count)
            return merged_ideas

        return all_ideas[:target_count]

    async def _synthesize_group(self, ideas: List[Dict], idx: int) -> IdeaGroup:
        ideas_text = "\n".join(_format_idea(i) for i in ideas)

        prompt = _GROUP_SYNTH_PROMPT.format(
            count=len(ideas),
            theme="auto-detect",
            ideas_text=ideas_text[:5000],
        )

        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        return IdeaGroup(
            group_id=f"group_{idx}",
            ideas=ideas,
            theme=data.get("theme", f"group_{idx}"),
            synthesis=data.get("synthesis", ""),
        )

    async def _merge_groups(
        self,
        groups: List[IdeaGroup],
        level: int,
    ) -> List[IdeaGroup]:
        merged = []
        pair_size = 4

        for i in range(0, len(groups), pair_size):
            batch = groups[i:i + pair_size]
            groups_text = "\n".join(_format_group(g, j) for j, g in enumerate(batch))

            prompt = f"""Merge these {len(batch)} group syntheses into ONE meta-synthesis.

{groups_text}

Return JSON:
{{
  "theme": "meta-theme",
  "synthesis": "2-3 sentence meta-synthesis capturing cross-group patterns and gaps"
}}
"""
            try:
                resp = await call_llm(self.llm, prompt)
                data = parse_json_response(resp)
                all_ideas_in_batch = []
                for g in batch:
                    all_ideas_in_batch.extend(g.ideas)
                merged.append(IdeaGroup(
                    group_id=f"meta_{level}_{i // pair_size}",
                    ideas=all_ideas_in_batch,
                    theme=data.get("theme", f"meta_{level}_{i}"),
                    synthesis=data.get("synthesis", ""),
                ))
            except Exception as e:
                logger.warning("Meta-merge failed at level %d: %s", level, e)
                all_ideas_in_batch = []
                for g in batch:
                    all_ideas_in_batch.extend(g.ideas)
                merged.append(IdeaGroup(
                    group_id=f"meta_{level}_{i // pair_size}",
                    ideas=all_ideas_in_batch,
                    theme=f"fallback_meta_{level}_{i}",
                    synthesis="; ".join(g.theme for g in batch),
                ))

        return merged

    async def _generate_from_synthesis(
        self,
        final_group: IdeaGroup,
        target_count: int,
    ) -> List[Dict]:
        prompt = _MERGE_PROMPT.format(
            count=1,
            groups_text=_format_group(final_group, 0),
            target_count=target_count,
        )

        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        ideas = data.get("ideas", [])
        logger.info("HierarchicalMerger: generated %d merged ideas", len(ideas))
        return ideas


class FocusedRetriever:
    def __init__(self, store=None):
        self.store = store

    def retrieve(
        self,
        all_ideas: List[Dict],
        mode: str = "all",
        query: str = "",
        category: str = "",
        top_k: int = 50,
        recent_n: int = 30,
    ) -> List[Dict]:
        if mode == "all":
            return all_ideas[:top_k]

        if mode == "recent":
            return all_ideas[-recent_n:]

        if mode == "category" and category:
            return self._by_category(all_ideas, category, top_k)

        if mode == "query" and query:
            return self._by_keywords(all_ideas, query, top_k)

        if mode == "diverse":
            return self._diverse_sample(all_ideas, top_k)

        return all_ideas[:top_k]

    def _by_category(self, ideas: List[Dict], category: str, top_k: int) -> List[Dict]:
        matched = [i for i in ideas if i.get("category", "").lower() == category.lower()]
        return matched[:top_k] if len(matched) >= top_k else matched + [
            i for i in ideas if i.get("category", "").lower() != category.lower()
        ][:top_k - len(matched)]

    def _by_keywords(self, ideas: List[Dict], query: str, top_k: int) -> List[Dict]:
        q_words = set(query.lower().split())
        scored = []
        for idea in ideas:
            text = f"{idea.get('title', '')} {idea.get('description', '')} {idea.get('methodology', '')}".lower()
            overlap = len(q_words & set(text.split()))
            if overlap > 0:
                scored.append((overlap, idea))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [i for _, i in scored[:top_k]]

    def _diverse_sample(self, ideas: List[Dict], top_k: int) -> List[Dict]:
        categories = {}
        for idea in ideas:
            cat = idea.get("category", "other")
            categories.setdefault(cat, []).append(idea)

        result = []
        per_cat = max(1, top_k // max(len(categories), 1))
        for cat, cat_ideas in categories.items():
            result.extend(cat_ideas[:per_cat])
            if len(result) >= top_k:
                break

        return result[:top_k]
