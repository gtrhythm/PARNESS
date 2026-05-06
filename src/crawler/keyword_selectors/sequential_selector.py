from typing import List

from ..base import BaseKeywordSelector
from ..models import KeywordResult


class SequentialSelector(BaseKeywordSelector):
    def __init__(self):
        self._index = 0

    def select(self, keywords: List[KeywordResult]) -> KeywordResult:
        if not keywords:
            raise ValueError("keywords list is empty")
        if self._index >= len(keywords):
            self._index = 0
        kw = keywords[self._index]
        self._index += 1
        return kw

    def selector_name(self) -> str:
        return "sequential"
