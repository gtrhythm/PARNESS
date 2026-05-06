from typing import List

from ..base import BaseKeywordSelector
from ..models import KeywordResult


class RoundRobinSelector(BaseKeywordSelector):
    def __init__(self):
        self._queue: List[KeywordResult] = []
        self._index = 0

    def set_sources(self, groups: List[List[KeywordResult]]):
        self._queue = []
        self._index = 0
        max_len = max((len(g) for g in groups), default=0)
        for i in range(max_len):
            for group in groups:
                if i < len(group):
                    self._queue.append(group[i])

    def select(self, keywords: List[KeywordResult]) -> KeywordResult:
        if not self._queue:
            self._queue = list(keywords)
            self._index = 0
        if not self._queue:
            raise ValueError("no keywords available")
        if self._index >= len(self._queue):
            self._index = 0
        kw = self._queue[self._index]
        self._index += 1
        return kw

    def selector_name(self) -> str:
        return "round_robin"
