from abc import ABC, abstractmethod
from typing import List

from ..models import KeywordResult


class BaseKeywordSelector(ABC):
    """KeywordSelector base class -- picks one keyword from a list, cycling forever."""

    @abstractmethod
    def select(self, keywords: List[KeywordResult]) -> KeywordResult:
        """
        Select one keyword from the list.
        When the list is exhausted, cycle back to the beginning.
        Never returns None.
        """
        raise NotImplementedError

    @abstractmethod
    def selector_name(self) -> str:
        raise NotImplementedError
