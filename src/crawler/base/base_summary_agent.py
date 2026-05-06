from abc import ABC, abstractmethod
from typing import List

from ..models import PaperContent, SearchIntent


class BaseSummaryAgent(ABC):
    """SummaryAgent base class -- receives SearchIntent, returns PaperContent list."""

    @abstractmethod
    async def fetch(self, intent: SearchIntent) -> List[PaperContent]:
        """Translate SearchIntent into platform-specific API calls and return papers."""
        raise NotImplementedError

    @abstractmethod
    def supported_domains(self) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    def rate_limit(self) -> float:
        """Return minimum seconds between requests."""
        raise NotImplementedError

    @property
    def agent_name(self) -> str:
        return self.__class__.__name__
