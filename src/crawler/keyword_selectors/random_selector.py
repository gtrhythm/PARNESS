import random
from typing import List

from ..base import BaseKeywordSelector
from ..models import KeywordResult


class RandomSelector(BaseKeywordSelector):
    def __init__(self, seed: int = 42):
        self._seed = seed
        self._pool: List[KeywordResult] = []

    def select(self, keywords: List[KeywordResult]) -> KeywordResult:
        if not keywords:
            raise ValueError("keywords list is empty")
        if not self._pool:
            self._pool = list(keywords)
            random.Random(self._seed).shuffle(self._pool)
            self._seed += 1
        return self._pool.pop(0)

    def selector_name(self) -> str:
        return "random"
