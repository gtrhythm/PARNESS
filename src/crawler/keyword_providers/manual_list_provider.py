from typing import List

from ..base import BaseKeywordProvider
from ..models import KeywordResult


class ManualListProvider(BaseKeywordProvider):
    def __init__(self, keywords: List[str] = None, domain: str = ""):
        self._keywords = keywords or []
        self._domain = domain

    async def generate(self, **kwargs) -> List[KeywordResult]:
        keywords = kwargs.get("keywords", self._keywords)
        domain = kwargs.get("domain", self._domain)
        return [
            KeywordResult(keyword=kw, confidence=1.0, source="manual", domain=domain)
            for kw in keywords
        ]

    def provider_name(self) -> str:
        return "manual_list"
