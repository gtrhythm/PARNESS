"""Paper-code retrieval service.

Indexes paper↔code mappings into the registry and serves search via the
registry's text index.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .analysis_registry import AnalysisRegistry
from .models import PaperCodeAnalysis

logger = logging.getLogger(__name__)


class PaperCodeRetrievalService:
    def __init__(
        self,
        llm_client=None,
        registry: Optional[AnalysisRegistry] = None,
    ):
        self.llm = llm_client
        self.registry = registry or AnalysisRegistry()

    async def index_analysis(self, analysis: PaperCodeAnalysis) -> int:
        """Persist mappings + reusable patterns into the registry. Returns the
        number of items registered."""
        indexed = 0
        for mapping in analysis.mappings:
            try:
                self.registry.add_mapping(analysis, mapping)
                indexed += 1
            except AttributeError:
                # Older registries may not have add_mapping; ignore quietly.
                break
            except Exception as exc:
                logger.warning("Failed to register mapping %s: %s", mapping.mapping_id, exc)
        for pattern in analysis.reusable_patterns:
            try:
                self.registry.add_pattern(analysis, pattern)
                indexed += 1
            except AttributeError:
                break
            except Exception as exc:
                logger.warning("Failed to register pattern %s: %s", pattern.pattern_id, exc)
        return indexed

    async def find_similar_implementations(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict]:
        return self._text_search(query, top_k, filters)

    async def get_implementation_guide(
        self,
        idea_description: str,
        top_k: int = 5,
    ) -> str:
        similar = await self.find_similar_implementations(idea_description, top_k=top_k)
        if not similar:
            return "No similar implementations found in the knowledge base."

        refs = []
        for i, s in enumerate(similar, 1):
            refs.append(
                f"\n### Reference {i}: {s.get('paper_title', '')} ({s.get('repo_id', '')})\n"
                f"Concept: {s.get('concept', '')}\n"
                f"Category: {s.get('concept_category', '')}\n"
                f"Implementation: {s.get('implementation_detail', '')[:500]}\n"
                f"Code Pattern: {s.get('code_pattern', '')[:200]}\n"
                f"Key Functions: {', '.join(s.get('key_functions', [])[:5])}\n"
                f"Tech Stack: {', '.join(s.get('tech_stack', [])[:5])}\n"
                f"Similarity: {s.get('score', 0.0):.3f}\n"
            )

        if not self.llm:
            return "## Similar Implementations\n" + "\n".join(refs)

        guide_prompt = (
            "Based on the following similar implementations from existing research code, "
            "provide a concrete implementation guide for this new idea:\n\n"
            f"## New Idea\n{idea_description}\n\n"
            f"## Similar Implementations\n{''.join(refs)}\n\n"
            "Provide:\n"
            "1. Recommended architecture and module structure\n"
            "2. Key components to implement and their patterns\n"
            "3. Suggested dependencies and tech stack\n"
            "4. Potential pitfalls and how to avoid them\n"
        )

        from ..idea_agents.llm_utils import call_llm
        return await call_llm(self.llm, guide_prompt)

    def _text_search(
        self,
        query: str,
        limit: int,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict]:
        if not self.registry:
            return []
        try:
            results = self.registry.search_mappings_text(query, limit=limit)
        except Exception as exc:
            logger.warning("Registry text search failed: %s", exc)
            return []
        if filters:
            results = [
                r for r in results
                if all(r.get(k) == v for k, v in filters.items())
            ]
        for r in results:
            r.setdefault("score", 0.5)
        return results
