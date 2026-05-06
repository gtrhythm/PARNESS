import json
import logging
from typing import Any, Dict, List, Optional

from ..base import BaseKeywordSelector
from ..models import KeywordResult

logger = logging.getLogger(__name__)


class LLMSelector(BaseKeywordSelector):
    def __init__(self, llm_client=None):
        self._llm_client = llm_client
        self._index = 0
        self._ranked: List[KeywordResult] = []

    def set_llm_client(self, llm_client):
        self._llm_client = llm_client

    def select(self, keywords: List[KeywordResult]) -> KeywordResult:
        if not keywords:
            raise ValueError("keywords list is empty")
        if not self._ranked or len(self._ranked) != len(keywords):
            self._ranked = list(keywords)
            self._index = 0
        if self._index >= len(self._ranked):
            self._index = 0
        kw = self._ranked[self._index]
        self._index += 1
        return kw

    async def rank_with_llm(
        self, keywords: List[KeywordResult], context: str = ""
    ) -> List[KeywordResult]:
        if not self._llm_client or not keywords:
            return keywords

        kw_list = [{"keyword": kw.keyword, "confidence": kw.confidence} for kw in keywords]
        prompt = (
            f"Given these search keywords: {json.dumps(kw_list)}\n"
        )
        if context:
            prompt += f"Context: {context}\n"
        prompt += (
            "Rank them by likely relevance for finding high-quality academic papers. "
            "Return a JSON array of objects with 'keyword' and 'confidence' fields, ordered best first."
        )
        try:
            response = await self._llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            items = json.loads(text)
            kw_map = {kw.keyword: kw for kw in keywords}
            ranked = []
            for item in items:
                kw_text = item.get("keyword", "")
                if kw_text in kw_map:
                    orig = kw_map[kw_text]
                    orig.confidence = float(item.get("confidence", orig.confidence))
                    ranked.append(orig)
            for kw in keywords:
                if kw not in ranked:
                    ranked.append(kw)
            self._ranked = ranked
            self._index = 0
            return ranked
        except Exception as e:
            logger.error("LLMSelector ranking failed: %s", e)
            return keywords

    def selector_name(self) -> str:
        return "llm"
