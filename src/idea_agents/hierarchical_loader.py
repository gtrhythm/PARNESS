import json
import logging
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .llm_utils import call_llm, parse_json_response
from .models import AgentKnowledgeBase, CompressedInsight, FullIdea, IdeaSeed
from .store import TieredKnowledgeStore

logger = logging.getLogger(__name__)


class LoadingLayer(Enum):
    METADATA = "metadata"
    SUMMARY = "summary"
    FULL = "full"


class HierarchicalLoader:
    def __init__(self, store: TieredKnowledgeStore, llm_client=None):
        self.store = store
        self.llm = llm_client

    async def load_insights(
        self,
        layer: LoadingLayer = LoadingLayer.METADATA,
        paper_ids: Optional[List[str]] = None,
    ) -> List[Dict]:
        all_insights = self.store.load_hot_insights()

        if paper_ids is not None:
            pid_set = set(paper_ids)
            all_insights = [i for i in all_insights if i.get("paper_id") in pid_set]

        if layer == LoadingLayer.METADATA:
            return [
                {
                    "paper_id": ins.get("paper_id", ""),
                    "title": ins.get("title", ""),
                    "year": ins.get("year", 0),
                    "core_insight": (ins.get("core_insight", "") or "").split("\n")[0][:200],
                }
                for ins in all_insights
            ]

        if layer == LoadingLayer.SUMMARY:
            return [
                {
                    "paper_id": ins.get("paper_id", ""),
                    "title": ins.get("title", ""),
                    "year": ins.get("year", 0),
                    "core_insight": ins.get("core_insight", ""),
                    "limitations": ins.get("limitations", []),
                    "open_questions": ins.get("open_questions", []),
                    "key_trick": ins.get("key_trick", ""),
                }
                for ins in all_insights
            ]

        return all_insights

    async def load_ideas(
        self,
        layer: LoadingLayer = LoadingLayer.METADATA,
        idea_ids: Optional[List[str]] = None,
        top_k: int = 50,
    ) -> List[Dict]:
        all_ideas = self.store.load_all_ideas()

        if idea_ids is not None:
            id_set = set(idea_ids)
            all_ideas = [
                i
                for i in all_ideas
                if i.get("title", "") in id_set
                or i.get("idea_id", "") in id_set
            ]

        all_ideas = all_ideas[:top_k]

        if layer == LoadingLayer.METADATA:
            return [
                {
                    "title": idea.get("title", ""),
                    "category": idea.get("category", ""),
                    "overall_score": idea.get("overall_score", 0.0),
                    "seed_type": idea.get("seed_type", ""),
                }
                for idea in all_ideas
            ]

        if layer == LoadingLayer.SUMMARY:
            return [
                {
                    "title": idea.get("title", ""),
                    "category": idea.get("category", ""),
                    "overall_score": idea.get("overall_score", 0.0),
                    "seed_type": idea.get("seed_type", ""),
                    "description": (idea.get("description", "") or "")[:500],
                    "methodology": (idea.get("methodology", "") or "")[:300],
                    "strengths": idea.get("strengths", []),
                    "weaknesses": idea.get("weaknesses", []),
                }
                for idea in all_ideas
            ]

        return all_ideas

    async def load_seeds(self, seed_type: Optional[str] = None) -> List[Dict]:
        kb = self.store.load_kb()
        seeds = kb.all_seeds()
        if seed_type:
            seeds = [s for s in seeds if s.seed_type == seed_type]
        return [s.to_dict() for s in seeds]

    async def load_with_model_parsing(
        self,
        query: str,
        initial_layer: LoadingLayer = LoadingLayer.METADATA,
        target_count: int = 30,
        max_layers: int = 3,
    ) -> List[Dict]:
        if self.llm is None:
            return await self.load_ideas(layer=LoadingLayer.FULL, top_k=target_count)

        ideas = await self.load_ideas(layer=LoadingLayer.METADATA)
        if not ideas:
            return []

        layer_order = [LoadingLayer.METADATA, LoadingLayer.SUMMARY, LoadingLayer.FULL]
        start_idx = layer_order.index(initial_layer)
        layers_to_process = layer_order[start_idx : start_idx + max_layers]

        current_ideas = ideas
        current_indices = list(range(len(ideas)))

        for layer_idx, target_layer in enumerate(layers_to_process):
            next_layer_idx = layer_idx + 1
            is_last_layer = next_layer_idx >= len(layers_to_process)

            if is_last_layer:
                full_ideas = await self.load_ideas(
                    layer=LoadingLayer.FULL,
                    top_k=len(current_ideas) + 100,
                )
                selected_titles = {i.get("title", "") for i in current_ideas}
                full_ideas = [
                    i for i in full_ideas if i.get("title", "") in selected_titles
                ]
                return full_ideas[:target_count]

            next_layer = layers_to_process[next_layer_idx]

            prompt = self._build_filter_prompt(
                query=query,
                ideas=current_ideas,
                target=min(target_count, len(current_ideas)),
                layer_idx=layer_idx,
            )

            try:
                response = await call_llm(self.llm, prompt)
                parsed = parse_json_response(response)
                selected = parsed.get("selected_indices", [])
            except Exception as e:
                logger.warning("LLM filtering failed at layer %s: %s", target_layer.value, e)
                break

            if not selected:
                logger.info("LLM selected no ideas at layer %s, stopping", target_layer.value)
                break

            selected = [i for i in selected if 0 <= i < len(current_ideas)]
            if not selected:
                break

            current_ideas_subset = [current_ideas[i] for i in selected]

            current_ideas = await self.load_ideas(
                layer=next_layer,
                top_k=len(current_ideas_subset) + 100,
            )

            subset_titles = {i.get("title", "") for i in current_ideas_subset}
            current_ideas = [
                i for i in current_ideas if i.get("title", "") in subset_titles
            ]

            if not current_ideas:
                break

        return current_ideas[:target_count]

    def _build_filter_prompt(
        self,
        query: str,
        ideas: List[Dict],
        target: int,
        layer_idx: int,
    ) -> str:
        numbered = "\n".join(
            f"[{i}] {json.dumps(idea, ensure_ascii=False)}"
            for i, idea in enumerate(ideas)
        )

        count = len(ideas)

        if layer_idx == 0:
            return (
                f"Given these {count} research idea summaries, "
                f"select the {target} most relevant to: \"{query}\"\n"
                f"Return JSON: {{\"selected_indices\": [0, 3, 7, ...]}}\n\n"
                f"{numbered}"
            )

        return (
            f"Given these {count} detailed idea summaries, "
            f"select the final {target} most promising for further development.\n"
            f"Return JSON: {{\"selected_indices\": [0, 2, 5, ...], "
            f"\"reasoning\": \"brief explanation\"}}\n\n"
            f"{numbered}"
        )

    async def load_progressive(
        self,
        callback: Callable,
        layers: Optional[List[LoadingLayer]] = None,
    ):
        if layers is None:
            layers = [LoadingLayer.METADATA, LoadingLayer.SUMMARY, LoadingLayer.FULL]

        for layer in layers:
            try:
                insights = await self.load_insights(layer=layer)
                ideas = await self.load_ideas(layer=layer)
                data = {"layer": layer, "insights": insights, "ideas": ideas}
                await callback(layer, data)
            except Exception as e:
                logger.error("Progressive loading failed at layer %s: %s", layer.value, e)
                raise
