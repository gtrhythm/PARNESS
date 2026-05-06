import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List

import httpx

from ..base import BaseKeywordProvider
from ..models import KeywordResult

logger = logging.getLogger(__name__)

ATOM_NS = "{http://www.w3.org/2005/Atom}"


class TrendKeywordProvider(BaseKeywordProvider):
    def __init__(self):
        pass

    async def generate(self, **kwargs) -> List[KeywordResult]:
        domain = kwargs.get("domain", "")
        source = kwargs.get("source", "arxiv_daily")
        days = kwargs.get("days", 7)
        max_keywords = kwargs.get("max_keywords", 10)

        if source == "arxiv_daily":
            return await self._from_arxiv_daily(domain, days, max_keywords)
        return []

    async def _from_arxiv_daily(
        self, domain: str, days: int, max_keywords: int
    ) -> List[KeywordResult]:
        from .taxonomy_expander import ARXIV_CATEGORY_MAP

        categories = ARXIV_CATEGORY_MAP.get(domain, [])
        if not categories:
            categories = ["cs.AI"]

        cat_query = " OR ".join(f"cat:{c}" for c in categories[:3])

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {
                    "search_query": cat_query,
                    "start": 0,
                    "max_results": 100,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                }
                resp = await client.get("https://export.arxiv.org/api/query", params=params)
                resp.raise_for_status()

                titles = self._parse_titles(resp.text)
                if not titles:
                    return []

                keyword_counts = self._extract_phrases(titles)
                results = []
                for phrase, count in keyword_counts.most_common(max_keywords):
                    results.append(KeywordResult(
                        keyword=phrase,
                        confidence=min(count / 10.0, 1.0),
                        source="arxiv_trend",
                        domain=domain,
                        extra={"count": count},
                    ))
                return results
        except Exception as e:
            logger.error("TrendKeywordProvider arxiv_daily failed: %s", e)
            return []

    def _parse_titles(self, xml_text: str) -> List[str]:
        titles = []
        try:
            root = ET.fromstring(xml_text)
            for entry in root.findall(f"{ATOM_NS}entry"):
                title_el = entry.find(f"{ATOM_NS}title")
                if title_el is not None and title_el.text:
                    titles.append(title_el.text.strip().replace("\n", " "))
        except ET.ParseError:
            pass
        return titles

    def _extract_phrases(self, titles: List[str]) -> dict:
        from collections import Counter
        stop_words = {
            "a", "an", "the", "of", "for", "in", "on", "with", "and", "or",
            "from", "to", "by", "via", "using", "based", "through",
        }
        phrase_counts = Counter()
        for title in titles:
            words = title.lower().split()
            for n in range(2, 5):
                for i in range(len(words) - n + 1):
                    phrase = " ".join(words[i:i+n])
                    if not all(w in stop_words for w in words[i:i+n]) and len(phrase) > 5:
                        phrase_counts[phrase] += 1
        return phrase_counts

    def provider_name(self) -> str:
        return "trend_keyword"
