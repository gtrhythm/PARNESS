from typing import List

from ..base import BaseKeywordSelector
from ..models import KeywordResult


class ConfidenceSelector(BaseKeywordSelector):
    def __init__(self):
        self._index = 0
        self._sorted: List[KeywordResult] = []

    def select(self, keywords: List[KeywordResult]) -> KeywordResult:
        if not keywords:
            raise ValueError("keywords list is empty")
        if not self._sorted or len(self._sorted) != len(keywords):
            self._sorted = sorted(keywords, key=lambda kw: kw.confidence, reverse=True)
            self._index = 0
        if self._index >= len(self._sorted):
            self._index = 0
        kw = self._sorted[self._index]
        self._index += 1
        return kw

    def selector_name(self) -> str:
        return "confidence"
