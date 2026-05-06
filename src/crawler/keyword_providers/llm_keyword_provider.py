import json
import logging
from typing import Any, Dict, List, Optional

from ..base import BaseKeywordProvider
from ..models import KeywordResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an academic research keyword generator. Given a research topic, idea, or description, generate a list of specific academic search keywords suitable for finding related papers on platforms like arXiv, PubMed, Semantic Scholar, etc.

Return a JSON array of objects with fields:
- "keyword": the search keyword/phrase (be specific, use academic terminology)
- "confidence": how relevant this keyword is (0.0-1.0)

Generate concise, targeted keywords that would find the most relevant papers. Prefer specific terms over broad ones."""


class LLMKeywordProvider(BaseKeywordProvider):
    def __init__(self, llm_client=None, max_keywords: int = 10):
        self._llm_client = llm_client
        self._max_keywords = max_keywords

    async def generate(self, **kwargs) -> List[KeywordResult]:
        content = kwargs.get("content", "")
        domain = kwargs.get("domain", "")
        max_keywords = kwargs.get("max_keywords", self._max_keywords)
        llm_client = kwargs.get("llm_client", self._llm_client)

        if not content:
            return []
        if not llm_client:
            logger.warning("LLMKeywordProvider: no llm_client provided, returning empty")
            return []

        user_prompt = f"Generate {max_keywords} academic search keywords"
        if domain:
            user_prompt += f" for the domain '{domain}'"
        user_prompt += f" based on the following content:\n\n{content}"

        try:
            response = await llm_client.chat(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
            )
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            items = json.loads(text)
            results = []
            for item in items[:max_keywords]:
                kw = item.get("keyword", item.get("keyword", ""))
                if isinstance(kw, str) and kw:
                    results.append(KeywordResult(
                        keyword=kw,
                        confidence=float(item.get("confidence", 0.5)),
                        source="llm",
                        domain=domain,
                    ))
            return results
        except Exception as e:
            logger.error("LLMKeywordProvider failed: %s", e)
            return []

    def provider_name(self) -> str:
        return "llm_keyword"
