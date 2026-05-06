from abc import ABC, abstractmethod
from typing import Any, Dict, List

from ..models import KeywordResult


class BaseKeywordProvider(ABC):
    """KeywordProvider base class -- produces a list of keywords from some source."""

    @abstractmethod
    async def generate(self, **kwargs) -> List[KeywordResult]:
        """Generate a list of keyword candidates."""
        raise NotImplementedError

    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError
