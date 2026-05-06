import json
import logging
from typing import Any, Dict, List, Optional

from ..base import BaseKeywordProvider
from ..models import KeywordResult

logger = logging.getLogger(__name__)


class KeywordMutator(BaseKeywordProvider):
    def __init__(self, llm_client=None):
        self._llm_client = llm_client

    async def generate(self, **kwargs) -> List[KeywordResult]:
        base_keywords = kwargs.get("base_keywords", [])
        strategy = kwargs.get("strategy", "combine")
        context = kwargs.get("context", "")
        domain = kwargs.get("domain", "")
        llm_client = kwargs.get("llm_client", self._llm_client)

        if not base_keywords:
            return []

        if strategy == "combine":
            return self._combine(base_keywords, domain)
        elif strategy == "broaden":
            return self._broaden(base_keywords, domain)
        elif strategy == "narrow":
            return self._narrow(base_keywords, context, domain)
        elif strategy == "neighbor":
            if llm_client:
                return await self._neighbor_llm(base_keywords, llm_client, domain)
            return self._neighbor_heuristic(base_keywords, domain)
        return []

    def _combine(self, keywords: List[str], domain: str) -> List[KeywordResult]:
        results = []
        for i in range(len(keywords)):
            for j in range(i + 1, len(keywords)):
                combined = f"{keywords[i]} {keywords[j]}"
                results.append(KeywordResult(
                    keyword=combined,
                    confidence=0.7,
                    source="mutator_combine",
                    domain=domain,
                ))
        return results

    def _broaden(self, keywords: List[str], domain: str) -> List[KeywordResult]:
        results = []
        for kw in keywords:
            words = kw.split()
            if len(words) > 2:
                for i in range(len(words)):
                    shorter = " ".join(words[:i] + words[i+1:])
                    results.append(KeywordResult(
                        keyword=shorter,
                        confidence=0.6,
                        source="mutator_broaden",
                        domain=domain,
                    ))
            if len(words) > 1:
                results.append(KeywordResult(
                    keyword=words[0],
                    confidence=0.5,
                    source="mutator_broaden",
                    domain=domain,
                ))
        return results

    def _narrow(self, keywords: List[str], context: str, domain: str) -> List[KeywordResult]:
        results = []
        for kw in keywords:
            if context:
                results.append(KeywordResult(
                    keyword=f"{kw} {context}",
                    confidence=0.8,
                    source="mutator_narrow",
                    domain=domain,
                ))
        return results

    async def _neighbor_llm(
        self, keywords: List[str], llm_client, domain: str
    ) -> List[KeywordResult]:
        prompt = (
            f"Given these search keywords: {', '.join(keywords)}\n"
            "Generate 5-10 semantically related but different academic search keywords "
            "that explore neighboring research directions.\n"
            "Return a JSON array of objects with 'keyword' and 'confidence' (0.0-1.0) fields."
        )
        try:
            response = await llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            items = json.loads(text)
            return [
                KeywordResult(
                    keyword=item["keyword"],
                    confidence=float(item.get("confidence", 0.5)),
                    source="mutator_neighbor_llm",
                    domain=domain,
                )
                for item in items
                if "keyword" in item
            ]
        except Exception as e:
            logger.error("KeywordMutator LLM neighbor failed: %s", e)
            return self._neighbor_heuristic(keywords, domain)

    def _neighbor_heuristic(self, keywords: List[str], domain: str) -> List[KeywordResult]:
        prefixes = ["survey of", "recent advances in", "benchmark for", "evaluation of"]
        suffixes = ["survey", "review", "benchmark", "evaluation", "analysis"]
        results = []
        for kw in keywords[:5]:
            for suffix in suffixes[:2]:
                results.append(KeywordResult(
                    keyword=f"{kw} {suffix}",
                    confidence=0.5,
                    source="mutator_neighbor",
                    domain=domain,
                ))
        return results

    def provider_name(self) -> str:
        return "keyword_mutator"
