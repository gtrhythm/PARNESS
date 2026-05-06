import logging
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class IdeaDeduplicator:
    def __init__(self, llm_client=None, similarity_threshold: float = 0.85):
        self.llm_client = llm_client
        self.similarity_threshold = similarity_threshold

    async def deduplicate(
        self,
        new_ideas: List[Dict],
        existing_ideas: Optional[List[Dict]] = None,
    ) -> Tuple[List[Dict], List[Tuple[Dict, Dict, float]]]:
        existing = existing_ideas or []

        if not new_ideas:
            return [], []

        new_embeddings = await self._get_embeddings(new_ideas)
        existing_embeddings = await self._get_embeddings(existing) if existing else []

        duplicates: List[Tuple[Dict, Dict, float]] = []
        kept: List[Dict] = []
        seen_keys: Set[str] = set()

        for i, idea in enumerate(new_ideas):
            title_key = idea.get("title", "").lower().strip()
            if title_key in seen_keys:
                continue

            is_dup = False
            emb_i = new_embeddings[i] if i < len(new_embeddings) else None

            if emb_i is not None:
                for j, ex_emb in enumerate(existing_embeddings):
                    sim = self._cosine_similarity(emb_i, ex_emb)
                    if sim >= self.similarity_threshold:
                        duplicates.append((idea, existing[j], sim))
                        is_dup = True
                        break

            if not is_dup:
                for j, prev_idea in enumerate(kept):
                    if j < len(new_embeddings):
                        prev_idx = new_ideas.index(prev_idea) if prev_idea in new_ideas else -1
                        if prev_idx >= 0 and prev_idx < len(new_embeddings):
                            sim = self._cosine_similarity(emb_i, new_embeddings[prev_idx])
                            if sim >= self.similarity_threshold:
                                duplicates.append((idea, prev_idea, sim))
                                is_dup = True
                                break
                    else:
                        sim = self._text_similarity(
                            idea.get("title", "") + " " + idea.get("description", ""),
                            prev_idea.get("title", "") + " " + prev_idea.get("description", ""),
                        )
                        if sim >= self.similarity_threshold:
                            duplicates.append((idea, prev_idea, sim))
                            is_dup = True
                            break

            if not is_dup:
                seen_keys.add(title_key)
                kept.append(idea)

        logger.info("Dedup: %d -> %d unique (%d duplicates)", len(new_ideas), len(kept), len(duplicates))
        return kept, duplicates

    async def _get_embeddings(self, ideas: List[Dict]) -> List[List[float]]:
        if not self.llm_client or not ideas:
            return []

        embeddings = []
        for idea in ideas:
            try:
                text = f"{idea.get('title', '')} {idea.get('description', '')}"
                if hasattr(self.llm_client, "embed"):
                    emb = await self.llm_client.embed(text)
                    embeddings.append(emb)
                else:
                    embeddings.append(self._simple_hash_embedding(text))
            except Exception as e:
                logger.warning("Embedding failed: %s", e)
                text = f"{idea.get('title', '')} {idea.get('description', '')}"
                embeddings.append(self._simple_hash_embedding(text))
        return embeddings

    @staticmethod
    def _simple_hash_embedding(text: str, dim: int = 64) -> List[float]:
        vec = [0.0] * dim
        words = text.lower().split()
        for i, w in enumerate(words):
            for c in w:
                idx = (ord(c) + i) % dim
                vec[idx] += 1.0
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        wa = set(a.lower().split())
        wb = set(b.lower().split())
        if not wa or not wb:
            return 0.0
        return len(wa & wb) / len(wa | wb)
